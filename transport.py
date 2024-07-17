"""
Base QUIC Server and Client class to handle rx-tx queues.
"""

import logging
from typing import Tuple

import asyncio
from aioquic.asyncio import serve, connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, StreamDataReceived

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QUICGatewayClient:
    class _QUICGatewayClientProtocol(QuicConnectionProtocol):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.quic_client_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
            self.quic_client_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()

        def quic_event_received(self, event):
            if isinstance(event, HandshakeCompleted):
                logger.info("QUIC handshake completed")
                asyncio.ensure_future(self.quic_writer())
                asyncio.ensure_future(self._keep_alive())

            # add received data to read queue (reader task)
            elif isinstance(event, StreamDataReceived):
                logger.info(f"Received from server-proxy, payload: '{event.data}' on stream '{event.stream_id}'")
                asyncio.ensure_future(self.quic_client_read_queue.put((event.stream_id, event.data)))

        async def send_data(self, stream_id, payload: bytes):
            await self.quic_client_write_queue.put((stream_id, payload))

        async def get_data(self):
            response = await self.quic_client_read_queue.get()
            return response

        async def _keep_alive(self):
            logger.info("Started Keep-Alive task (will send every 10 seconds)")
            while True:
                await asyncio.sleep(10)  # Send ping every 10 seconds
                await self.ping()

        async def quic_writer(self):
            while True:
                stream_id, payload = await self.quic_client_write_queue.get()
                logger.info(f"Sending to server-proxy, payload: '{payload}' over stream '{stream_id}'")
                self._quic.send_stream_data(stream_id, payload)
                self.transmit()

    def __init__(self, quic_server_host, quic_server_port, disable_cert_verification=True):
        self.quic_server_host, self.quic_server_port = quic_server_host, quic_server_port
        self.disable_cert_verification = disable_cert_verification
        self.quic_client = None

    async def run(self):
        """
        Can be overridden by subclasses to implement the main loop. But should call self.init_quic_client()
        :return:
        """
        tx_task = asyncio.create_task(self.tx_message_dispatcher())
        rx_task = asyncio.create_task(self.rx_message_dispatcher())

        await self.init_quic_client()
        await asyncio.gather(tx_task, rx_task)

    async def init_quic_client(self):
        """
        Creates a QUIC client and runs infinite loop to send data based on write queue.
        :return:
        """
        logger.info(
            f"Starting QUIC transport client, remote server = ({self.quic_server_host}:{self.quic_server_port})")
        configuration = QuicConfiguration(is_client=True)
        configuration.verify_mode = not self.disable_cert_verification  # Disable certificate verification for testing

        while True:
            async with connect(self.quic_server_host, self.quic_server_port, configuration=configuration,
                               create_protocol=self._QUICGatewayClientProtocol) as quic_client:
                self.quic_client = quic_client
                await quic_client.wait_closed()

                # restart if quic_client gets disconnected
                logger.info("QUIC client disconnected, retrying")
                await asyncio.sleep(1)

    async def tx_message_dispatcher(self):
        """
        Sends data to QUIC gateway server. To be overridden by subclasses.
        :return:
        """
        logger.info("TX Dispatcher started")
        while True:
            if self.quic_client:
                stream_id, payload = self.quic_client._quic.get_next_available_stream_id(), b"DUMMY DATA"
                logger.info(f"TX Dispatcher - {stream_id}: {payload.decode()}")
                await self.quic_client.send_data(stream_id, payload)
                await asyncio.sleep(5)
            else:
                logger.error("TX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        """
        Handle response from QUIC server. To be overridden by subclasses.
        :return:
        """
        logger.info("RX Dispatcher started")
        while True:
            if self.quic_client:
                stream_id, data = await self.quic_client.get_data()
                logger.info(f"RX Dispatcher - {stream_id}: {data.decode()}")
            else:
                logger.error("RX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)


class QUICGatewayServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.quic_server_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.quic_server_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.quic_writer_task = None
        self.tx_task = None
        self.rx_task = None

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            print("QUIC Handshake completed")
            asyncio.ensure_future(self.init_tasks())

        elif isinstance(event, StreamDataReceived):
            logger.info(f"Received from client-proxy, payload: '{event.data}' on stream '{event.stream_id}'")
            asyncio.ensure_future(self.quic_server_read_queue.put((event.stream_id, event.data)))

    async def init_tasks(self):
        self.quic_writer_task = self.quic_writer()
        self.tx_task = asyncio.create_task(self.tx_message_dispatcher())
        self.rx_task = asyncio.create_task(self.rx_message_dispatcher())
        await asyncio.gather(self.quic_writer_task, self.tx_task, self.rx_task)

    async def send_data(self, stream_id, payload: bytes):
        await self.quic_server_write_queue.put((stream_id, payload))

    async def get_data(self):
        data = await self.quic_server_read_queue.get()
        return data

    async def quic_writer(self):
        while True:
            stream_id, payload = await self.quic_server_write_queue.get()
            logger.info(f"Sending to server-proxy, payload: '{payload}' over stream '{stream_id}'")
            self._quic.send_stream_data(stream_id, payload)
            self.transmit()

    async def tx_message_dispatcher(self):
        """
        Sends data to QUIC gateway client. To be overridden by subclasses.
        :return:
        """
        logger.info("TX Dispatcher started")

    async def rx_message_dispatcher(self):
        """
        Handle response from QUIC client. To be overridden by subclasses.
        :return:
        """
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.get_data()
                logger.info(f"RX Dispatcher - {stream_id}: {data.decode()}")
                await self.send_data(stream_id, f"{data.decode()} BACK".encode())
            except Exception as e:
                logger.error("RX Dispatcher - error in received data...")
                logger.exception(e)


async def init_quic_server(quic_server_host, quic_server_port, certfile, keyfile, disable_cert_verification,
                           server_protocol):
    logger.info(f"Starting QUIC transport server ({quic_server_host}:{quic_server_port})")
    configuration = QuicConfiguration(is_client=False)
    configuration.verify_mode = not disable_cert_verification
    configuration.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return await serve("0.0.0.0", 4433, configuration=configuration, create_protocol=server_protocol)

