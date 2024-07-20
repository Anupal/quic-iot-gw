import logging
import random
import socket
import string
import time
import multiprocessing as mp

import quic_iot_gateway.mqtt_sn as mqtt_sn
from quic_iot_gateway.utils import setup_logger

setup_logger(logging_level=logging.WARNING)
logger = logging.getLogger(__name__)

GW_HOST, GW_PORT = "localhost", 1883
NUM_CLIENTS = 500
REQUESTS = 50
MESSAGE_SIZE_RANGE = (50, 500)  # bytes
STARTING_PORT = 31001
NUM_TOPICS = 10


def generate_bytes(n):
    return "".join(
        [random.choice(string.printable) for _ in range(n)]
    )


def connect_message(client_id, qos):
    return mqtt_sn.encoder.encode(**{
        'type': mqtt_sn.MessageType.CONNECT,
        'flags': {
            'dup': False,
            'qos': qos,
            'retain': False,
            'will': False,
            'clean_session': False,
            'topic_type': 0
        },
        'protocol_id': 1,
        'duration': 10,
        'client_id': client_id
    })


def register_message(topic_name):
    return mqtt_sn.encoder.encode(**{
        'type': mqtt_sn.MessageType.REGISTER,
        'topic_id': 0,
        'msg_id': random.randint(1, 65535),
        'topic_name': topic_name
    })


def publish_message(topic_id, data, qos):
    pub_dict = {
        'type': mqtt_sn.MessageType.PUBLISH,
        'flags': {
            'dup': False,
            'qos': qos,
            'retain': False,
            'will': False,
            'clean_session': False,
            'topic_type': 0x00
        },
        'topic_id': topic_id,
        'msg_id': random.randint(1, 65535),
        'data': data
    }
    return mqtt_sn.encoder.encode(**pub_dict)


def send_request(client, message, recv=True):
    try:
        client.sendto(message, (GW_HOST, GW_PORT))
        if recv:
            client.settimeout(5.0)
            response, server_address = client.recvfrom(1024)
            return mqtt_sn.decoder.decode(response)
    except Exception as e:
        logger.exception(e)
        return


def start_mqtt_sn_client(index, results):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.bind(("localhost", STARTING_PORT + index))

    response = send_request(client, connect_message(f"client{1}", 0))
    if not response or response["return_code"] != mqtt_sn.ReturnCode.ACCEPTED:
        logger.error(f"Client{index} failed to connect")
        return
    logger.info(f"Client{index} connected")

    logger.info(f"Client{index} registering topics.")
    topic_name_to_id = {}
    for i in range(NUM_TOPICS):
        time.sleep(random.random())
        response = send_request(client, register_message(f"test{i}"))
        if not response or response["return_code"] != mqtt_sn.ReturnCode.ACCEPTED:
            logger.error(f"Client{index} failed to register topic test{i}")
        topic_name_to_id[f"test{i}"] = response["topic_id"]

    logger.info(f"Client{index} registered, topic ID mappings:\n{topic_name_to_id}")

    logger.info(f"Client{index} sending requests.")
    success = 0
    for _ in range(REQUESTS):
        i = random.randint(0, NUM_TOPICS - 1)
        time.sleep(random.random() + random.random())
        if f"test{i}" in topic_name_to_id:
            response = send_request(client,
                publish_message(
                    topic_name_to_id[f"test{i}"],
                    generate_bytes(random.randint(*MESSAGE_SIZE_RANGE)),
                    1
                )
            )
            if not response or response["return_code"] != mqtt_sn.ReturnCode.ACCEPTED:
                logger.error(f"Client{index} failed to PUBLISH topic test{i}")
            else:
                success += 1

    client.close()

    results.put((index, success))


def main():
    results = mp.Queue()
    p_mqtt_sn_clients = [
        mp.Process(target=start_mqtt_sn_client, args=(i, results), daemon=True)
        for i in range(1, NUM_CLIENTS + 1)
    ]

    logger.info(f"Starting MQTT-SN Clients...")
    for client in p_mqtt_sn_clients:
        client.start()
    while results.qsize() != NUM_CLIENTS: ...

    table = []
    logger.warning("Retrieving results:")
    for i in range(NUM_CLIENTS):
        table.append(results.get())

    for client in p_mqtt_sn_clients:
        client.join()

    table.sort(key=lambda x: x[0])
    for index, result in table:
        logger.warning(f"| {index:<5} | {result:<5} |")


if __name__ == "__main__":
    main()
