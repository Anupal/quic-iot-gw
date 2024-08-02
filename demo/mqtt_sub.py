import logging
import json
import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


sensor_data = {}


def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode())
        sensor_id = data.pop("id")
        sensor_data[sensor_id] = data

        with open("sensor_data_mqtt.json", "w") as f:
            json.dump(sensor_data, f, indent=2)
    except Exception:
        ...


def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected with result code {rc}")
    # Subscribe to the topic
    client.subscribe("data")


def start_mqtt_sub():
    while True:
        try:
            client = mqtt.Client()
            client.on_connect = on_connect
            client.on_message = on_message
            client.connect("mqtt-broker", 1883, 60)

            client.loop_start()

            # Keep the script running to listen for messages
            try:
                while True:
                    pass
            except KeyboardInterrupt:
                pass

            # Stop the network loop and disconnect
            client.loop_stop()
            client.disconnect()
        except Exception:
            logger.info("Retrying MQTT connection to broker")


start_mqtt_sub()
