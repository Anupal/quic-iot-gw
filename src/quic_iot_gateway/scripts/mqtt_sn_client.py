import socket
import argparse
import logging
import string
import random
import time
import multiprocessing as mp

import quic_iot_gateway.mqtt_sn as mqtt_sn
from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


def process_args():
    parser = argparse.ArgumentParser(description='MQTT-SN client input params')
    parser.add_argument('--message_size_range', type=str, default='50,500',
                        help='Range of message sizes in bytes (e.g., "50,500")')
    parser.add_argument('--mqtt-sn-gw-host', type=str, default='localhost',
                        help='Host address (e.g., "localhost)')
    parser.add_argument('--mqtt-sn-gw-port', type=int, default=1883,
                        help='Port number (e.g., 1883)')

    parser.add_argument('--log-level', default='INFO',
                        help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    parser.add_argument('--num-clients', default=500,
                        help='Define the number of coap clients that will connect to the server')
    parser.add_argument('--num-requests', default=50,
                        help='Define the number of requests made per coap client.')
    parser.add_argument('--num-topics', default=10,
                        help='Define the number of topics to shuffle for coap clients.')
    parser.add_argument('--starting-port', default=31001,
                        help='Define the starting port number to be used by coap clients.')

    # Parse arguments
    args = parser.parse_args()

    # Process the message size range
    message_size_range = tuple(map(int, args.message_size_range.split(',')))
    mqtt_sn_gw_host = args.mqtt_sn_gw_host
    mqtt_sn_gw_port = int(args.mqtt_sn_gw_port)

    log_level = getattr(logging, args.log_level.upper(), logging.WARNING)

    return (
        message_size_range,
        mqtt_sn_gw_host,
        mqtt_sn_gw_port,
        log_level, int(args.num_clients), int(args.num_requests),
        int(args.num_topics), int(args.starting_port)
    )


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


def send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, message, recv=True):
    try:
        client.sendto(message, (mqtt_sn_gw_host, mqtt_sn_gw_port))
        if recv:
            client.settimeout(5.0)
            response, server_address = client.recvfrom(1024)
            return mqtt_sn.decoder.decode(response)
    except Exception as e:
        logger.exception(e)
        return


def start_mqtt_sn_client(index, mqtt_sn_gw_host, mqtt_sn_gw_port, num_requests, num_topics, message_size_range,
                         starting_port, results):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.bind(("0.0.0.0", starting_port + index))

    response = send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, connect_message(f"client{index}", 0))
    if not response or response["return_code"] != mqtt_sn.ReturnCode.ACCEPTED:
        logger.error(f"Client{index} failed to connect")
        return
    logger.debug(f"Client{index} connected")

    logger.debug(f"Client{index} registering topics.")
    topic_name_to_id = {}
    for i in range(num_topics):
        time.sleep(random.random())
        response = send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, register_message(f"test{i}"))
        if not response or response["return_code"] != mqtt_sn.ReturnCode.ACCEPTED:
            logger.error(f"Client{index} failed to register topic test{i}")
        topic_name_to_id[f"test{i}"] = response["topic_id"]

    logger.debug(f"Client{index} registered, topic ID mappings:\n{topic_name_to_id}")

    logger.debug(f"Client{index} sending requests.")
    success = 0
    for _ in range(num_requests):
        i = random.randint(0, num_topics - 1)
        time.sleep(random.random() + random.random())
        if f"test{i}" in topic_name_to_id:
            response = send_request(client,
                mqtt_sn_gw_host, mqtt_sn_gw_port,
                publish_message(
                    topic_name_to_id[f"test{i}"],
                    generate_bytes(random.randint(*message_size_range)),
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
    message_size_range, mqtt_sn_gw_host, mqtt_sn_gw_port, log_level, num_clients, \
        num_requests, num_topics, starting_port = process_args()
    setup_logger(log_level)

    try:
        mqtt_sn_gw_host = socket.gethostbyname(mqtt_sn_gw_host)
    except Exception:
        logger.exception(f"Failed to resolve host '{mqtt_sn_gw_host}'")
        exit(1)

    while True:
        results = mp.Queue()
        p_mqtt_sn_clients = [
            mp.Process(target=start_mqtt_sn_client, args=(i, mqtt_sn_gw_host, mqtt_sn_gw_port, num_requests, num_topics,
                                                          message_size_range, starting_port, results), daemon=True)
            for i in range(1, num_clients + 1)
        ]

        logger.info("Sleeping for 5 seconds...")
        time.sleep(5)
        logger.info(f"Starting MQTT-SN Clients...")
        for client in p_mqtt_sn_clients:
            client.start()
        while results.qsize() != num_clients: ...

        table = []
        logger.info("Retrieving results:")
        for i in range(num_clients):
            table.append(results.get())

        for client in p_mqtt_sn_clients:
            client.join()

        table.sort(key=lambda x: x[0])
        for index, result in table:
            logger.warning(f"| {index:<5} | {result:<5} |")

        logger.info(f"Result: {sum([res[1] for res in table]) / num_clients:.2f}")
