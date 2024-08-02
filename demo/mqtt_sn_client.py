import socket
import random

import mqtt_sn
import json
import time

import threading

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


def send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, message, recv=True, retries=2):
    retries += 1
    try:
        while retries > 0:
            if retries < 3: logger.info(f"Retransmission {3 - retries}")
            try:
                client.sendto(message, (mqtt_sn_gw_host, mqtt_sn_gw_port))
                if recv:
                    client.settimeout(5.0)
                    response, server_address = client.recvfrom(1024)
                    return mqtt_sn.decoder.decode(response)
            except TimeoutError:
                retries -= 1
    except Exception as e:
        logger.exception(e)
        return


starting_port = 34500
mqtt_sn_gw_host = "qig-client"
mqtt_sn_gw_port = 1883


def mqtt_sn_client(index):
    protocol = "MQTT"
    sensor_type = random.choice(['Temperature', 'Humidity', 'Pressure'])
    lat = 53.3 + random.uniform(0.04, 0.05)
    lon = -6.3 + random.uniform(0.04, 0.05)

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.bind(("0.0.0.0", starting_port + index))

    response = send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, connect_message(f"democ-{index}", 0))


    response = send_request(client, mqtt_sn_gw_host, mqtt_sn_gw_port, register_message(f"data"))
    if response:
        topic_id = int(response["topic_id"])
    else:
        topic_id = 1

    while True:
        if sensor_type == 'Temperature':
            reading = f"{random.uniform(20, 25):.1f}°C"
        elif sensor_type == 'Humidity':
            reading = f"{random.randint(30, 60)}%"
        elif sensor_type == 'Pressure':
            reading = f"{random.randint(1000, 1020)} hPa"

        health = random.choice(['Good', 'Fair', 'Poor'])
        payload = json.dumps({
            'id': index,
            'type': sensor_type,
            'protocol': protocol,
            'reading': reading,
            'health': health,
            'lat': lat,
            'lon': lon
        })

        response = send_request(client,
            mqtt_sn_gw_host, mqtt_sn_gw_port,
            publish_message(
                topic_id,
                payload,
                1
            )
        )
        time.sleep(5)

def td_mqtt_sn_client(index):
    mqtt_sn_client(index)


if __name__ == "__main__":
    time.sleep(5)
    tds = []
    for index in range(6, 11):
        td = threading.Thread(target=td_mqtt_sn_client, args=(index, ))
        tds.append(td)
        td.start()

    for td in tds:
        td.join()
