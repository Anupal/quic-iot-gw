import logging
import asyncio
import asyncio_dgram
from mqtt_sn.message import MQTTSNPacketDecoder, MQTTSNPacketEncoder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Gateway:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.dgram_read_queue = asyncio.Queue()
        self.dgram_write_queue = asyncio.Queue()
        self.decoder = MQTTSNPacketDecoder()
        self.encoder = MQTTSNPacketEncoder()

    async def run(self):
        logger.info("Starting MQTT gateway server on {}:{}".format(self.host, self.port))
        udp_stream = await asyncio_dgram.bind((self.host, self.port))
        self.reader_task = asyncio.create_task(self.datagram_reader(udp_stream))
        self.writer_task = asyncio.create_task(self.datagram_writer(udp_stream))
        self.message_handler_task = asyncio.create_task(self.message_handler())

        await asyncio.gather(self.reader_task, self.message_handler_task, self.writer_task)

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

    async def message_handler(self):
        logger.info("Message handler started")
        while True:
            data, remote_addr = await self.dgram_read_queue.get()
            logger.info(f"Message Handler:  {data}, {remote_addr}")
            # decode the message
            decoded_message = self.decoder.decode(data)
            logger.info(f"Decoded message: {decoded_message}")

            reencoded_message = self.encoder.encode(**decoded_message)

            # echo the message back
            await self.dgram_write_queue.put((reencoded_message, remote_addr))

    async def stop(self):
        self.reader_task.cancel()
        self.message_handler_task.cancel()

