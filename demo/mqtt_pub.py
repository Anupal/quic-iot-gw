import paho.mqtt.client as mqtt
import random
import threading
import json
import time


def mqtt_client(index):
    protocol = "MQTT"
    sensor_type = random.choice(['Temperature', 'Humidity', 'Pressure'])
    lat = 53.3 + random.uniform(0.04, 0.05)
    lon = -6.3 + random.uniform(0.04, 0.05)

    def on_connect(client, userdata, flags, rc):
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

        # Publish a message to a topic
        client.publish("data", payload)

    while True:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.connect("127.0.0.1", 1883, 60)
        client.loop_start()
        time.sleep(1)
        client.loop_stop()
        client.disconnect()

        time.sleep(4)


def td_mqtt_client(index):
    mqtt_client(index)



if __name__ == "__main__":
    tds = []
    for index in range(6, 11):
        td = threading.Thread(target=td_mqtt_client, args=(index, ))
        tds.append(td)
        td.start()

    for td in tds:
        td.join()
