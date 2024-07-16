import logging

import aiocoap
import asyncio
import asyncio_dgram

import transport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    async def handle_read_message(self):
        """
        Read data from read queue and save request information like MID, client address.
        """

    async def handle_write_message(self, data):
        """
        Write to write queue and send it to application protocol io.
        """


class CoAPClientContext(ClientContext):
    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port
        self._pending_requests = {}

    async def run(self):
        logger.info(f"Starting CoAP Proxy server on {self.host}:{self.port}")
        udp_stream = await asyncio_dgram.bind((self.host, self.port))

        self.reader_task = asyncio.create_task(self.application_reader(udp_stream))
        self.writer_task = asyncio.create_task(self.application_writer(udp_stream))

        await asyncio.gather(self.reader_task, self.writer_task)

    async def application_reader(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("Datagram reader started")
        while True:
            data, client_addr = await udp_stream.recv()
            logger.info(
                f"Received datagram length = {len(data)}, data = {data}, source = {client_addr}"
            )
            await self.read_queue.put((data, client_addr))

    async def application_writer(self, udp_stream: asyncio_dgram.aio.DatagramServer):
        logger.info("Datagram writer started")
        while True:
            data, client_addr = await self.write_queue.get()
            logger.info(
                f"Sending datagram length = {len(data)}, data = {data}, destination = {client_addr}"
            )
            await udp_stream.send(data, client_addr)

    async def handle_read_message(self):
        data, client_address = await self.read_queue.get()
        logger.info(f"Handling CoAP request from {client_address}")
        coap_data = aiocoap.Message.decode(data)
        self._pending_requests[(coap_data.token, coap_data.mid)] = client_address
        return data

    async def handle_write_message(self, data):
        logger.info(f"Handling CoAP response")
        coap_data = aiocoap.Message.decode(data)
        logger.info(f"Decoded CoAP response = {coap_data}")
        if (coap_data.token, coap_data.mid) in self._pending_requests:
            client_address = self._pending_requests.pop((coap_data.token, coap_data.mid))
            await self.write_queue.put((data, client_address))


class IoTGatewayClient(transport.QUICGatewayClient):
    def __init__(self, *args, coap_context, **kwargs):
        super().__init__(*args, **kwargs)

        self.coap_context = coap_context
        asyncio.ensure_future(coap_context.run())

    async def run(self):
        coap_tx_task = asyncio.create_task(self.coap_tx_message_dispatcher())
        coap_rx_task = asyncio.create_task(self.coap_rx_message_dispatcher())

        await self.init_quic_client()
        await asyncio.gather(coap_tx_task, coap_rx_task)

    async def coap_tx_message_dispatcher(self):
        logger.info("CoAP TX Dispatcher started")
        while True:
            if self.quic_client:
                try:
                    payload = await self.coap_context.handle_read_message()
                    stream_id = self.quic_client._quic.get_next_available_stream_id()

                    logger.info(f"TX Dispatcher - {stream_id}: {payload}")
                    await self.quic_client.send_data(stream_id, payload)

                except Exception as e:
                    logger.error("TX Dispatcher - Error occurred when handling CoAP message...")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def coap_rx_message_dispatcher(self):
        logger.info("CoAP RX Dispatcher started")
        while True:
            if self.quic_client:
                try:
                    stream_id, data = await self.quic_client.get_data()
                    logger.info(f"RX Dispatcher - {stream_id}: {data}")
                    await self.coap_context.handle_write_message(data)
                except Exception as e:
                    logger.error("RX Dispatcher - Error occurred when handling CoAP message...")
                    logger.exception(e)
            else:
                logger.error("RX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)
