import asyncio
import logging
import struct
from typing import Tuple, Union, Dict

logger = logging.getLogger(__name__)


class TCPGatewayClient:
    class _TCPGatewayClientProtocol(asyncio.Protocol):
        def __init__(self, index, tcp_client_read_queue: asyncio.Queue, tcp_client_write_queue: asyncio.Queue):
            self.index = index
            self.tcp_client_read_queue = tcp_client_read_queue
            self.tcp_client_write_queue = tcp_client_write_queue
            self.transport = None
            self.wait_closed = asyncio.Future()
            self.writer_task = None

        def connection_made(self, transport):
            self.transport = transport
            logger.info("TCP connection established")
            self.writer_task = asyncio.create_task(self.tcp_writer())

        def data_received(self, data):
            stream_id = struct.unpack('!H', data[:2])[0]
            data = data[2:]
            logger.debug(f"TCP:{self.index} Received from server-proxy, payload: '{repr(data)}' on stream '{stream_id}'")
            asyncio.ensure_future(self.tcp_client_read_queue.put((stream_id, data)))

        def connection_lost(self, exc):
            logger.warning("TCP connection lost")
            if exc:
                logger.error(f"Connection lost due to {exc}")
            self.writer_task.cancel()
            self.wait_closed.set_result(True)

        async def send_data(self, stream_id, payload: bytes):
            await self.tcp_client_write_queue.put((stream_id, payload))

        async def get_data(self):
            response = await self.tcp_client_read_queue.get()
            return response

        async def tcp_writer(self):
            while True:
                try:
                    stream_id, data = await self.tcp_client_write_queue.get()
                    logger.debug(f"TCP:{self.index} Sending to server-proxy, payload '{data}' over stream '{stream_id}'")
                    self.transport.write(struct.pack('!H', stream_id) + data)
                except Exception as e:
                    logger.error("TCP writer error")
                    logger.exception(e)

    def __init__(self, tcp_server_host, tcp_server_port, num_tcp_clients=10):
        self.tcp_server_host = tcp_server_host
        self.tcp_server_port = tcp_server_port
        self.num_tcp_clients = num_tcp_clients
        self._tcp_clients: Dict[int, Union[None, TCPGatewayClient._TCPGatewayClientProtocol]] = {
            i: None for i in range(self.num_tcp_clients)
        }
        self.tcp_clients = []

        self.io_tasks = []
        self.io_tasks_funcs = []
        self.tcp_client_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.tcp_client_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self._stream_id = 0

    @property
    def tcp_client(self):
        if self.tcp_clients:
            tcp_client_index = self.tcp_clients.pop(0)
            self.tcp_clients.append(tcp_client_index)
            return self._tcp_clients[tcp_client_index]

    async def run(self):
        self.io_tasks_funcs = [self.tx_message_dispatcher, self.rx_message_dispatcher]
        for index in range(self.num_tcp_clients):
            asyncio.ensure_future(self.init_tcp_client(index))
        await self.start_io_tasks()

    async def init_tcp_client(self, index: int):
        logger.info(f"Starting TCP client {index}, server = ({self.tcp_server_host}:{self.tcp_server_port})")

        while True:
            try:
                loop = asyncio.get_event_loop()
                tcp_client = self._TCPGatewayClientProtocol(index, self.tcp_client_read_queue,
                                                            self.tcp_client_write_queue)
                try:
                    transport, protocol = await loop.create_connection(
                        lambda: tcp_client,
                        self.tcp_server_host, self.tcp_server_port
                    )
                    self._tcp_clients[index] = tcp_client
                    self.tcp_clients.append(index)
                    logger.info(f"TCP client {index} connected")
                    await tcp_client.wait_closed
                    logger.error(f"TCP client {index} disconnected, retrying after 1 second")
                    self.tcp_clients.remove(index)
                    self._tcp_clients[index] = None
                    transport.close()
                    # self.cancel_io_tasks()

                except asyncio.CancelledError:
                    ...

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Unable to connect TCP client {index}, retrying after 5 seconds.")
                logger.exception(e)
                await asyncio.sleep(5)

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
            tcp_client = self.tcp_client
            if tcp_client:
                try:
                    stream_id, payload = self._get_next_available_stream_id(), b"DUMMY DATA"
                    logger.debug(f"TX Dispatcher - {stream_id}: {payload.decode()}")
                    await tcp_client.send_data(stream_id, payload)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error("TX Dispatcher error")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no TCP client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        """
        Handle response from TCP server. To be overridden by subclasses.
        :return:
        """
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.tcp_client_read_queue.get()
                logger.debug(f"RX Dispatcher - {stream_id}: {repr(data.decode())}")
            except Exception as e:
                logger.error("RX Dispatcher error")
                logger.exception(e)


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
        stream_id = int(struct.unpack('!H', data[:2])[0])
        data = data[2:]
        logger.debug(f"Received from client-proxy, payload: '{repr(data)}' on stream '{stream_id}'")
        asyncio.ensure_future(self.tcp_server_read_queue.put((stream_id, data)))

    def connection_lost(self, exc):
        logger.warning("TCP connection lost with client")
        if exc:
            logger.error(f"Connection lost due to {exc}")

    async def init_tasks(self):
        self.tcp_writer_task = self.tcp_writer()
        self.tx_task = asyncio.create_task(self.tx_message_dispatcher())
        self.rx_task = asyncio.create_task(self.rx_message_dispatcher())
        await asyncio.gather(self.tcp_writer_task, self.tx_task, self.rx_task)

    async def send_data(self, stream_id, payload: bytes):
        await self.tcp_server_write_queue.put((stream_id, payload))

    async def get_data(self):
        data = await self.tcp_server_read_queue.get()
        return data

    async def tcp_writer(self):
        while True:
            stream_id, payload = await self.tcp_server_write_queue.get()
            logger.debug(f"Sending to client-proxy, payload: '{repr(payload)}' over stream '{stream_id}'")
            self.transport.write(struct.pack('!H', stream_id) + payload)

    async def tx_message_dispatcher(self):
        """
        Sends data to TCP gateway client. To be overridden by subclasses.
        :return:
        """
        logger.info("TX Dispatcher started")

    async def rx_message_dispatcher(self):
        """
        Handle response from TCP client. To be overridden by subclasses.
        :return:
        """
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.get_data()
                logger.debug(f"RX Dispatcher: {repr(data.decode())}")
                await self.send_data(stream_id, f"{data.decode()} BACK".encode())
            except Exception as e:
                logger.error("RX Dispatcher - error in received data...")
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
