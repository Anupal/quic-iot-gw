import json
from typing import Tuple

import aiocoap
import asyncio
import asyncio_dgram
import aiomqtt

import quic_iot_gateway.mqtt_sn as mqtt_sn
from quic_iot_gateway.utils import setup_logger

logger = setup_logger(__name__)


class ClientContext:
    def __init__(self):
        self.read_queue = asyncio.Queue()
        self.write_queue = asyncio.Queue()
        self.reader_task = None
        self.writer_task = None

    async def run(self):
        """
        To be overridden by subclasses. Setup IO stream for application protocol, Setup rx/tx queues and tasks.
        """
        ...

    async def application_reader(self, *args, **kwargs):
        """
        Setup reader task to run in background. This will put received data from application protocol io in read_queue.
        """
        ...

    async def application_writer(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        """
        Setup writer task to run in background. This will read data in write_queue and send it to application protocol io.
        """

    async def handle_read_message(self, get_next_stream_id) -> Tuple[bytes, int]:
        """
        Read data from read queue and save request information like MID, client address.
        """

    async def handle_write_message(self, data, stream_id):
        """
        Write to write queue and send it to application protocol io.
        """

    def is_valid(self, data) -> bool:
        ...

    def reset(self):
        ...


class MQTTSNGWClientContext(ClientContext):
    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port
        self._device_stream_map = {}
        self._stream_device_map = {}

        self.mqtt_sn_clients = {}
        self.registered_topics = mqtt_sn.RegisteredTopics()

    async def run(self):
        logger.info(f"Starting MQTT-SN-GW on {self.host}:{self.port}")

        try:
            udp_stream = await asyncio_dgram.bind((self.host, self.port))
        except OSError as e:
            logger.error(f"Unable to reserve ({self.host}:{self.port}) for MQTT-SN-GW as it is in use, exiting...")
            return

        self.reader_task = asyncio.create_task(self.application_reader(udp_stream))
        self.writer_task = asyncio.create_task(self.application_writer(udp_stream))

        await asyncio.gather(self.reader_task, self.writer_task)

    async def application_reader(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("MQTT-SN-GW Datagram reader started")
        while True:
            data, client_addr = await udp_stream.recv()
            logger.info(
                f"MQTT-SN-GW - Received datagram length = {len(data)}, data = {data}, source = {client_addr}"
            )
            await self.read_queue.put((data, client_addr))

    async def application_writer(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("MQTT-SN-GW Datagram writer started")
        while True:
            data, client_addr = await self.write_queue.get()
            logger.info(
                f"MQTT-SN-GW - Sending datagram length = {len(data)}, data = {data}, destination = {client_addr}"
            )
            await udp_stream.send(data, client_addr)

    async def handle_read_message(self, get_next_stream_id: callable):
        data, client_address = await self.read_queue.get()

        try:
            decoded_message = mqtt_sn.decoder.decode(data)
        except ValueError as e:
            logger.warning(f"Unable to decode MQTT-SN-GW message: {data}, error = {e}")
            return

        logger.info(f"Decoded MQTT-SN message: {decoded_message}")

        if decoded_message["type"] == mqtt_sn.MessageType.CONNECT:
            asyncio.ensure_future(self.connect_handler(decoded_message, client_address))

        elif decoded_message["type"] == mqtt_sn.MessageType.REGISTER:
            if client_address in self.mqtt_sn_clients:
                asyncio.ensure_future(
                    self.register_handler(decoded_message, self.mqtt_sn_clients[client_address]["client_id"],
                                          client_address))
            else:
                logger.warning(f"REGISTER received from unknown client '{client_address}'")
                logger.warning(f"Sending DISCONNECT message to {client_address}")
                await self.write_queue.put((mqtt_sn.encoder.encode(
                    type=mqtt_sn.MessageType.DISCONNECT
                ), client_address))

        elif decoded_message["type"] == mqtt_sn.MessageType.PUBLISH:
            if client_address in self.mqtt_sn_clients:
                forward = await self.publish_handler(decoded_message, client_address)
                # If message is valid, then forward over QUIC
                if forward:
                    if client_address in self._device_stream_map:
                        stream_id = self._device_stream_map[client_address]
                    else:
                        stream_id = get_next_stream_id()
                        self._device_stream_map[client_address] = stream_id
                        self._stream_device_map[stream_id] = client_address

                    # send MQTT packet data as JSON, so it can be published by the Server context
                    mqtt_publish_dict = {
                        "type": "PUBLISH",
                        "topic_name": self.registered_topics.topic_id_to_name(
                            self.mqtt_sn_clients[client_address]["client_id"],
                            decoded_message["topic_id"]
                        ),
                        "data": decoded_message["data"],
                        "qos": decoded_message["flags"]["qos"],
                        "retain": decoded_message["flags"]["retain"],
                        "msg_id": decoded_message["msg_id"],
                        "protocol": "MQTT-SN",
                    }
                    mqtt_publish_json = json.dumps(mqtt_publish_dict).encode()
                    return mqtt_publish_json, stream_id
            else:
                logger.warning(f"PUBLISH received from unknown client '{client_address}'")
                logger.warning(f"Sending DISCONNECT message to {client_address}")
                await self.write_queue.put((mqtt_sn.encoder.encode(
                    type=mqtt_sn.MessageType.DISCONNECT
                ), client_address))

        elif decoded_message["type"] == mqtt_sn.MessageType.DISCONNECT:
            if client_address in self.mqtt_sn_clients:
                await self.write_queue.put((mqtt_sn.encoder.encode(
                    type=mqtt_sn.MessageType.DISCONNECT
                ), client_address))
                self.mqtt_sn_clients.pop(client_address)
                stream_id = self._device_stream_map.pop(client_address)
                self._stream_device_map.pop(stream_id)

    async def connect_handler(self, message, remote_addr):
        logger.info(f"Save MQTT-SN client '{remote_addr}' with client id' {message['client_id']}'.")
        self.mqtt_sn_clients[remote_addr] = {
            "client_id": message["client_id"], "duration": message["duration"]
        }
        connack_message = mqtt_sn.encoder.encode(
            type=mqtt_sn.MessageType.CONNACK,
            return_code=mqtt_sn.ReturnCode.ACCEPTED
        )
        logger.info(f"Sending CONNACK message: {connack_message} to {remote_addr}")
        await self.write_queue.put((connack_message, remote_addr))

    async def register_handler(self, message, client_id, remote_addr):
        topic_name = message["topic_name"]
        topic_id = self.registered_topics.add_topic(client_id, topic_name)
        logger.info(f"Registered MQTT-SN client '{remote_addr}' -> '{client_id}' with topic name '{topic_name}' -> id '{topic_id}'")
        regack_message = mqtt_sn.encoder.encode(
            type=mqtt_sn.MessageType.REGACK,
            topic_id=topic_id,
            msg_id=message["msg_id"],
            return_code=mqtt_sn.ReturnCode.ACCEPTED
        )
        logger.info(f"Sending REGACK message: {regack_message} to {remote_addr}")
        await self.write_queue.put((regack_message, remote_addr))

    async def publish_handler(self, message, client_address):
        topic_id = message["topic_id"]
        client_id = self.mqtt_sn_clients[client_address]["client_id"]
        topic_name = self.registered_topics.topic_id_to_name(client_id, topic_id)
        if topic_name:
            return True
        else:
            logger.warning(f"No associated topic id '{topic_id}' found for MQTT-SN client '{client_id}'")
            puback_message = mqtt_sn.encoder.encode(
                type=mqtt_sn.MessageType.PUBACK,
                topic_id=topic_id,
                msg_id=message["msg_id"],
                return_code=mqtt_sn.ReturnCode.INVALID_TOPIC
            )
            logger.warning(f"Sending PUBACK message: {puback_message} to {client_address}")
            await self.write_queue.put((puback_message, client_address))

        return False

    async def handle_write_message(self, data, stream_id):
        logger.info(f"Handling MQTT response received on stream id {stream_id}")
        try:
            payload = json.loads(data)
            if payload["type"] == "PUBACK":
                if stream_id not in self._stream_device_map:
                    logger.warning(f"No device associated stream id '{stream_id}' found for MQTT-SN.")
                    return

                client_address = self._stream_device_map[stream_id]
                client_id = self.mqtt_sn_clients[client_address]["client_id"]
                topic_id = self.registered_topics.topic_name_to_id(client_id, payload["topic_name"])

                if not topic_id:
                    logger.warning(f"No associated topic id for topic name '{payload['topic_name']}' found for MQTT-SN.")
                    return

                puback_message = mqtt_sn.encoder.encode(
                    type=mqtt_sn.MessageType.PUBACK,
                    topic_id=topic_id,
                    msg_id=payload["msg_id"],
                    return_code=payload["return_code"]
                )
                logger.info(f"Sending PUBACK message: {puback_message} to {client_address}")
                await self.write_queue.put((puback_message, client_address))
        except Exception as e:
            logger.error(f"Unable to handle MQTT response from server-proxy: {repr(data)}")
            logger.exception(e)


    def is_valid(self, data):
        try:
            mqtt_sn.decoder.decode(data)
            return True
        except Exception:
            ...
        try:
            payload = json.loads(data.decode())
            return payload["protocol"] == "MQTT-SN"
        except Exception:
            return False

    def reset(self):
        logger.info("Resetting MQTT-SN context - cleared stream ids")
        self._device_stream_map = {}


class CoAPClientContext(ClientContext):
    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port
        self._device_stream_map = {}
        self._stream_device_map = {}

    async def run(self):
        logger.info(f"Starting CoAP Proxy server on {self.host}:{self.port}")
        try:
            udp_stream = await asyncio_dgram.bind((self.host, self.port))
        except OSError as e:
            logger.error(f"Unable to reserve ({self.host}:{self.port}) for CoAP Proxy as it is in use, exiting...")
            return

        self.reader_task = asyncio.create_task(self.application_reader(udp_stream))
        self.writer_task = asyncio.create_task(self.application_writer(udp_stream))

        await asyncio.gather(self.reader_task, self.writer_task)

    async def application_reader(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("CoAP Proxy Datagram reader started")
        while True:
            data, client_addr = await udp_stream.recv()
            logger.info(
                f"CoAP Proxy - Received datagram length = {len(data)}, data = {data}, source = {client_addr}"
            )
            await self.read_queue.put((data, client_addr))

    async def application_writer(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("CoAP Proxy Datagram writer started")
        while True:
            data, client_addr = await self.write_queue.get()
            logger.info(
                f"CoAP Proxy - Sending datagram length = {len(data)}, data = {data}, destination = {client_addr}"
            )
            await udp_stream.send(data, client_addr)

    async def handle_read_message(self, get_next_stream_id: callable):
        data, client_address = await self.read_queue.get()
        if client_address in self._device_stream_map:
            stream_id = self._device_stream_map[client_address]
        else:
            stream_id = get_next_stream_id()
            self._device_stream_map[client_address] = stream_id
            self._stream_device_map[stream_id] = client_address

        logger.info(f"Handling CoAP request from {client_address}")
        return data, stream_id

    async def handle_write_message(self, data, stream_id):
        logger.info(f"Handling CoAP response")
        if self.is_valid(data):
            coap_data = aiocoap.Message.decode(data)
            logger.info(f"Decoded CoAP response = {coap_data}")
            if stream_id in self._stream_device_map:
                client_address = self._stream_device_map[stream_id]
                await self.write_queue.put((data, client_address))
        else:
            logger.warning(f"Invalid CoAP response received on stream id {stream_id}")

    def is_valid(self, data):
        try:
            message = aiocoap.Message.decode(data)
            # check code type is Unknown if parsing passes
            return "Unknown" not in message.code.name_printable
        except:
            return False

    def reset(self):
        logger.info("Resetting CoAP context - cleared pending requests, stream ids")
        self._device_stream_map = {}


class ServerContext:
    def __init__(self):
        self.read_queue = asyncio.Queue()
        self.write_queue = asyncio.Queue()

    async def run(self):
        """
        To be overridden by subclasses. Setup IO stream for application protocol, Setup rx/tx queues and tasks.
        """
        ...

    async def handle_read_message(self, data):
        """
        Handle data received from application protocol io.
        """

    async def handle_write_message(self, data):
        """
        Handle data received from QUIC and send it to application protocol io.
        """

    def is_valid(self, data) -> bool:
        ...


class CoAPServerContext(ServerContext):
    async def handle_read_message(self, data):
        ...

    async def handle_write_message(self, data):
        coap_request = aiocoap.Message.decode(data)
        if coap_request.opt.proxy_uri is None:
            logger.warning("Proxy-URI option missing in request")
            response = aiocoap.Message(code=aiocoap.BAD_OPTION, mtype=aiocoap.Type.ACK)
        else:
            target_uri = coap_request.opt.proxy_uri
            logger.info(f"Proxying request to {target_uri}")

            # Forward the CoAP request to the actual server
            protocol = await aiocoap.Context.create_client_context()
            proxy_request = aiocoap.Message(code=coap_request.code, uri=target_uri, payload=coap_request.payload)

            try:
                coap_response = await protocol.request(proxy_request).response
                logger.info(f"Forwarded request to {target_uri}, received response: {coap_response} payload: "
                            f"'{coap_response.payload}'")
                response = coap_response
            except Exception as e:
                logger.error(f"Failed to get response from server: {e}")
                response = aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR, mtype=aiocoap.Type.ACK)

        response.mid = coap_request.mid
        response.token = coap_request.token
        return response.encode()

    def is_valid(self, data) -> bool:
        try:
            message = aiocoap.Message.decode(data)
            # check code type is Unknown if parsing passes
            return "Unknown" not in message.code.name_printable
        except:
            return False


class MQTTSNGWServerContext(ServerContext):
    def __init__(self, broker_address, broker_port):
        super().__init__()
        self._broker_address = broker_address
        self._broker_port = broker_port
        self.mqtt_client = None

    async def run(self):
        while True:
            logger.info(f"Connecting to MQTT Broker ({self._broker_address}:{self._broker_port})")
            try:
                async with aiomqtt.client.Client(self._broker_address, self._broker_port) as mqtt_client:
                    self.mqtt_client = mqtt_client

                    async for message in self.mqtt_client.messages:
                        logger.info(f"MQTT Message from Broker: {message.topic} {message.payload}")
                        await self.read_queue.put((message.topic, message.payload))
            except Exception as e:
                self.mqtt_client = None
                logger.error("Disconnected from MQTT Broker, retrying after 5 seconds.")
                logger.exception(e)
                await asyncio.sleep(5)

            self.mqtt_client = None

    async def handle_read_message(self, data):
        mqtt_message = await self.read_queue.get()
        mqtt_publish_dict = {
            "type": "PUBLISH",
            "topic_name": str(mqtt_message.topic),
            "data": str(mqtt_message.paylaod),
            "qos": mqtt_message.qos,
            "retain": mqtt_message.retain,
            "protocol": "MQTT-SN",
        }
        return json.dumps(mqtt_publish_dict).encode()

    async def handle_write_message(self, data):
        mqtt_message_dict = json.loads(data.decode())
        if self.mqtt_client:
            if mqtt_message_dict["type"] == "PUBLISH":
                logger.info("Forwarding MQTT PUBLISH to broker")
                try:
                    await self.mqtt_client.publish(
                        mqtt_message_dict["topic_name"],
                        mqtt_message_dict["data"],
                        qos=mqtt_message_dict["qos"],
                        retain=mqtt_message_dict["retain"],
                    )
                    logger.info("MQTT PUBLISH successful, sending PUBACK back to client-proxy.")
                    mqtt_puback_dict = {
                        "type": "PUBACK",
                        "topic_name": mqtt_message_dict["topic_name"],
                        "return_code": mqtt_sn.ReturnCode.ACCEPTED,
                        "msg_id": mqtt_message_dict["msg_id"],
                        "protocol": "MQTT-SN",
                    }
                    return json.dumps(mqtt_puback_dict).encode()
                except Exception as e:
                    logger.error(f"Failed to publish to broker")
                    logger.exception(e)
                    mqtt_puback_dict = {
                        "type": "PUBACK",
                        "topic_name": mqtt_message_dict["topic_name"],
                        "return_code": mqtt_sn.ReturnCode.CONGESTION,
                        "msg_id": mqtt_message_dict["msg_id"],
                        "protocol": "MQTT-SN",
                    }
                    return json.dumps(mqtt_puback_dict).encode()
            if mqtt_message_dict["type"] == "SUBSCRIBE":
                logger.info(f"Subscribing to topic '{mqtt_message_dict['topic_name']}' broker")
                try:
                    await self.mqtt_client.subscribe(mqtt_message_dict["topic_name"], qos=mqtt_message_dict["qos"])
                except Exception as e:
                    logger.error(f"Failed to subscribe to broker with topic '{mqtt_message_dict['topic_name']}'")
                    logger.exception(e)
                # todo: handle return for subscribe
        else:
            logger.error(f"Cannot forward MQTT message: {data}. Not connected to MQTT broker.")

    def is_valid(self, data) -> bool:
        try:
            payload = json.loads(data.decode())
            return payload["protocol"] == "MQTT-SN"
        except:
            return False