import asyncio
import logging
import struct
from typing import Tuple

logger = logging.getLogger(__name__)


class TCPGatewayClient:
    class _TCPGatewayClientProtocol(asyncio.Protocol):
        def __init__(self, parent, tcp_client_read_queue: asyncio.Queue, tcp_client_write_queue: asyncio.Queue):
            self.parent = parent
            self.tcp_client_read_queue = tcp_client_read_queue
            self.tcp_client_write_queue = tcp_client_write_queue
            self.transport = None

        def connection_made(self, transport):
            self.transport = transport
            logger.info("TCP connection established")
            self.parent.client = True
            asyncio.ensure_future(self.tcp_writer())

        def data_received(self, data):
            stream_id = struct.unpack('!H', data[:2])[0]
            data = data[2:]
            logger.debug(f"Received from server, payload {data} on stream id {stream_id}")
            asyncio.ensure_future(self.tcp_client_read_queue.put((stream_id, data)))

        def connection_lost(self, exc):
            logger.warning("TCP connection lost")
            if exc:
                logger.error(f"Connection lost due to {exc}")
            self.parent.client = False

            self.parent.cancel_io_tasks()

        async def tcp_writer(self):
            while self.parent.client:
                try:
                    stream_id, data = await self.tcp_client_write_queue.get()
                    logger.debug(f"Sending to server: {data}")
                    self.transport.write(struct.pack('!H', stream_id) + data)
                except Exception as e:
                    logger.error("TCP writer error")
                    logger.exception(e)

    def __init__(self, tcp_server_host, tcp_server_port):
        self.tcp_server_host = tcp_server_host
        self.tcp_server_port = tcp_server_port
        self.client = False
        self.io_tasks = []
        self.io_tasks_funcs = []
        self.tcp_client_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.tcp_client_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self._stream_id = 0

    async def run(self):
        self.io_tasks_funcs = [self.tx_message_dispatcher, self.rx_message_dispatcher]
        await self.init_tcp_client()

    async def init_tcp_client(self):
        logger.info(f"Starting TCP client, server = ({self.tcp_server_host}:{self.tcp_server_port})")

        while True:
            if not self.client:
                try:
                    loop = asyncio.get_event_loop()
                    try:
                        transport, protocol = await loop.create_connection(
                            lambda: self._TCPGatewayClientProtocol(self, self.tcp_client_read_queue, self.tcp_client_write_queue),
                            self.tcp_server_host, self.tcp_server_port
                        )

                        await self.start_io_tasks()
                        transport.close()
                    except asyncio.CancelledError:
                        self.client = False
                    logger.error("TCP client disconnected, retrying after 1 second")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error("Unable to connect to TCP server, retrying after 5 seconds.")
                    logger.exception(e)
                    await asyncio.sleep(5)
            else:
                await asyncio.sleep(1)

    async def start_io_tasks(self):
        io_tasks = []
        for func in self.io_tasks_funcs:
            io_tasks.append(asyncio.create_task(func()))
        self.io_tasks = io_tasks
        await asyncio.gather(*io_tasks)

    def cancel_io_tasks(self):
        for task in self.io_tasks:
            task.cancel()

    def _get_next_available_stream_id(self):
        old = self._stream_id
        self._stream_id += 1
        return old

    async def tx_message_dispatcher(self):
        logger.info("TX Dispatcher started")
        while True:
            if self.client:
                stream_id, payload = self._get_next_available_stream_id(), b"DUMMY DATA"
                logger.debug(f"TX Dispatcher - {stream_id}: {payload.decode()}")
                await self.tcp_client_write_queue.put((stream_id, payload))
                await asyncio.sleep(5)
            else:
                logger.error("TX Dispatcher - no TCP client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        logger.info("RX Dispatcher started")
        while True:
            if self.client:
                stream_id, data = await self.tcp_client_read_queue.get()
                logger.debug(f"RX Dispatcher - Received: {data.decode()}")
            else:
                logger.error("RX Dispatcher - no TCP client available, retrying after 5 seconds.")
                await asyncio.sleep(5)


class TCPGatewayServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.tcp_server_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.tcp_server_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.transport = None
        self.tcp_writer_task = None
        self.tx_task = None
        self.rx_task = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info("TCP connection established with client")
        asyncio.ensure_future(self.init_tasks())

    def data_received(self, data):
        stream_id = struct.unpack('!H', data[:2])[0]
        data = data[2:]
        logger.debug(f"Received from client, payload {data} on stream id {stream_id}")
        asyncio.ensure_future(self.tcp_server_read_queue.put((stream_id, data)))

    def connection_lost(self, exc):
        logger.warning("TCP connection lost with client")
        if exc:
            logger.error(f"Connection lost due to {exc}")

    async def init_tasks(self):
        self.tx_task = asyncio.create_task(self.tx_message_dispatcher())
        self.rx_task = asyncio.create_task(self.rx_message_dispatcher())
        await asyncio.gather(self.tx_task, self.rx_task)

    async def tx_message_dispatcher(self):
        logger.info("TX Dispatcher started")
        while True:
            stream_id, data = await self.tcp_server_write_queue.get()
            logger.debug(f"Sending to client: {data}")
            self.transport.write(struct.pack('!H', stream_id) + data)

    async def rx_message_dispatcher(self):
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.tcp_server_read_queue.get()
                logger.debug(f"RX Dispatcher: {data.decode()}")
                response = f"{data.decode()} BACK".encode()
                await self.tcp_server_write_queue.put((stream_id, response))
            except Exception as e:
                logger.error("RX Dispatcher exception")
                logger.exception(e)


async def init_tcp_server(tcp_server_host, tcp_server_port, server_protocol):
    logger.info(f"Starting TCP server ({tcp_server_host}:{tcp_server_port})")

    loop = asyncio.get_event_loop()
    server = await loop.create_server(
        lambda: server_protocol(),
        tcp_server_host, tcp_server_port
    )

    async with server:
        await server.serve_forever()
