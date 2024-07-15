import logging
import asyncio
import asyncio_dgram
from mqtt_sn.message import MQTTSNPacketDecoder, MQTTSNPacketEncoder, MessageType, ReturnCode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RegisteredTopics:
    def __init__(self):
        self.clients = {}
        self.clients_rev = {}
        self._topic_id_tracker = {}

    def add_topic(self, client_id, topic_name):
        if client_id not in self.clients:
            topic_id = self._next_topic_id(client_id)
            self.clients[client_id] = {topic_name: topic_id}
            self.clients_rev[client_id] = {topic_id: topic_name}
            return topic_id
        elif topic_name in self.clients[client_id]:
            return self.clients[client_id][topic_name]
        else:
            topic_id = self._next_topic_id(client_id)
            self.clients[client_id][topic_name] = topic_id
            self.clients_rev[client_id][topic_id] = topic_name
            return topic_id

    def topic_id_to_name(self, client_id, topic_id):
        return self.clients_rev.get(client_id, {}).get(topic_id, None)

    def _next_topic_id(self, client_id):
        topic_id = self._topic_id_tracker.get(client_id, 1)
        self._topic_id_tracker[client_id] = topic_id + 1
        return topic_id


class Gateway:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.dgram_read_queue = asyncio.Queue()
        self.dgram_write_queue = asyncio.Queue()
        self.mqtt_tasks = set()
        self.decoder = MQTTSNPacketDecoder()
        self.encoder = MQTTSNPacketEncoder()
        self.mqtt_sn_clients = {}
        self.registered_topics = RegisteredTopics()

    async def run(self):
        logger.info("Starting MQTT gateway server on {}:{}".format(self.host, self.port))
        udp_stream = await asyncio_dgram.bind((self.host, self.port))
        self.reader_task = asyncio.create_task(self.datagram_reader(udp_stream))
        self.writer_task = asyncio.create_task(self.datagram_writer(udp_stream))
        self.message_handler_task = asyncio.create_task(self.message_dispatcher())

        # Execute MQTT relay tasks
        while True:
            if self.mqtt_tasks:
                finished_tasks, _ = await asyncio.wait(
                    self.mqtt_tasks, timeout=0.5
                )

                for task in finished_tasks:
                    try:
                        task.result()
                    except Exception as e:
                        logger.exception(f"Exception while executing MQTT task {e}")

                self.mqtt_tasks.difference_update(finished_tasks)
            else:
                await asyncio.sleep(0.5)

    async def datagram_reader(self, udp_stream: asyncio_dgram.aio.DatagramStream):
        logger.info("Datagram reader started")
        while True:
            data, remote_addr = await udp_stream.recv()
            logger.info(
                f"Received datagram length = {len(data)}, data = {data}, source = {remote_addr}"
            )
            await self.dgram_read_queue.put((data, remote_addr))

    async def datagram_writer(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("Datagram writer started")
        while True:
            data, remote_addr = await self.dgram_write_queue.get()
            logger.info(
                f"Sending datagram length = {len(data)}, data = {data}, destination = {remote_addr}"
            )
            await udp_stream.send(data, remote_addr)

    async def message_dispatcher(self):
        logger.info("Message handler started")
        while True:
            data, remote_addr = await self.dgram_read_queue.get()
            logger.info(f"Message Handler:  {data}, {remote_addr}")
            # decode the message
            decoded_message = self.decoder.decode(data)

            if not decoded_message:
                # todo: handle unsupported/malformed packets
                ...
            logger.info(f"Decoded message: {decoded_message}")

            if decoded_message["type"] == MessageType.CONNECT:
                self.mqtt_tasks.add(
                    asyncio.create_task(self.connect_handler(decoded_message, remote_addr))
                )

            elif decoded_message["type"] == MessageType.REGISTER:
                if remote_addr in self.mqtt_sn_clients:
                    self.mqtt_tasks.add(
                        asyncio.create_task(self.register_handler(decoded_message, self.mqtt_sn_clients[remote_addr]["client_id"], remote_addr))
                    )
                else:
                    logger.error(f"REGISTER received from unknown client '{remote_addr}'")
                    logger.info(f"Sending DISCONNECT message to {remote_addr}")
                    await self.dgram_write_queue.put((self.encoder.encode(
                        type=MessageType.DISCONNECT
                    ), remote_addr))
            elif decoded_message["type"] == MessageType.PUBLISH:
                if remote_addr in self.mqtt_sn_clients:
                    self.mqtt_tasks.add(
                        asyncio.create_task(self.publish_handler(decoded_message, self.mqtt_sn_clients[remote_addr]["client_id"], remote_addr))
                    )
                else:
                    logger.error(f"PUBLISH received from unknown client '{remote_addr}'")
                    logger.info(f"Sending DISCONNECT message to {remote_addr}")
                    await self.dgram_write_queue.put((self.encoder.encode(
                        type=MessageType.DISCONNECT
                    ), remote_addr))

    async def connect_handler(self, message, remote_addr):
        logger.info(f"Add MQTT-SN client '{remote_addr}' -> '{message['client_id']}'")
        self.mqtt_sn_clients[remote_addr] = {
            "client_id": message["client_id"], "duration": message["duration"]
        }
        connack_message = self.encoder.encode(
            type=MessageType.CONNACK,
            return_code=ReturnCode.ACCEPTED
        )
        logger.info(f"Sending CONNACK message: {connack_message} to {remote_addr}")
        await self.dgram_write_queue.put((connack_message , remote_addr))

    async def register_handler(self, message, client_id, remote_addr):
        topic_name = message["topic_name"]
        topic_id = self.registered_topics.add_topic(client_id, topic_name)
        logger.info(f"Registered MQTT-SN client '{remote_addr}' -> '{client_id}' with topic name '{topic_name}' -> id '{topic_id}'")
        regack_message = self.encoder.encode(
            type=MessageType.REGACK,
            topic_id=topic_id,
            msg_id=message["msg_id"],
            return_code=ReturnCode.ACCEPTED
        )
        logger.info(f"Sending REGACK message: {regack_message} to {remote_addr}")
        await self.dgram_write_queue.put((regack_message, remote_addr))

    async def publish_handler(self, message, client_id, remote_addr):
        topic_id = message["topic_id"]
        topic_name = self.registered_topics.topic_id_to_name(client_id, topic_id)
        if topic_name:
            # todo: implement MQTT relay
            logger.info("Forwarded message to MQTT broker (details)")
            puback_message = self.encoder.encode(
                type=MessageType.PUBACK,
                topic_id=topic_id,
                msg_id=message["msg_id"],
                return_code=ReturnCode.ACCEPTED
            )
            logger.info(f"Sending PUBACK message: {puback_message} to {remote_addr}")
            await self.dgram_write_queue.put((puback_message, remote_addr))
        else:
            logger.error(f"No associated topic id '{topic_id}' found for MQTT-SN client '{client_id}'")
            puback_message = self.encoder.encode(
                type=MessageType.PUBACK,
                topic_id=topic_id,
                msg_id=message["msg_id"],
                return_code=ReturnCode.INVALID_TOPIC
            )
            logger.info(f"Sending PUBACK message: {puback_message} to {remote_addr}")
            await self.dgram_write_queue.put((puback_message, remote_addr))

    async def stop(self):
        self.reader_task.cancel()
        self.message_handler_task.cancel()

