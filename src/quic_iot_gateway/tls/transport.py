import asyncio
import logging
import struct
from typing import Tuple, Union, Dict
import ssl

logger = logging.getLogger(__name__)


class TLSGatewayClient:
    class _TLSGatewayClientProtocol(asyncio.Protocol):
        def __init__(self, index, tls_client_read_queue: asyncio.Queue, tls_client_write_queue: asyncio.Queue):
            self.index = index
            self.tls_client_read_queue = tls_client_read_queue
            self.tls_client_write_queue = tls_client_write_queue
            self.transport = None
            self.wait_closed = asyncio.Future()
            self.writer_task = None

        def connection_made(self, transport):
            self.transport = transport
            logger.info("TLS connection established")
            self.writer_task = asyncio.create_task(self.tls_writer())

        def data_received(self, data):
            stream_id = struct.unpack('!H', data[:2])[0]
            data = data[2:]
            logger.debug(
                f"TLS:{self.index} Received from server-proxy, payload: '{repr(data)}' on stream '{stream_id}'")
            asyncio.ensure_future(self.tls_client_read_queue.put((stream_id, data)))

        def connection_lost(self, exc):
            logger.warning("TLS connection lost")
            if exc:
                logger.error(f"Connection lost due to {exc}")
            self.writer_task.cancel()
            self.wait_closed.set_result(True)

        async def send_data(self, stream_id, payload: bytes):
            await self.tls_client_write_queue.put((stream_id, payload))

        async def get_data(self):
            response = await self.tls_client_read_queue.get()
            return response

        async def tls_writer(self):
            while True:
                try:
                    stream_id, data = await self.tls_client_write_queue.get()
                    logger.debug(
                        f"TLS:{self.index} Sending to server-proxy, payload '{data}' over stream '{stream_id}'")
                    self.transport.write(struct.pack('!H', stream_id) + data)
                except Exception as e:
                    logger.error("TLS writer error")
                    logger.exception(e)

    def __init__(self, tls_server_host, tls_server_port, num_tls_clients=10, disable_cert_verification=True):
        self.tls_server_host = tls_server_host
        self.tls_server_port = tls_server_port
        self.num_tls_clients = num_tls_clients
        self.disable_cert_verification = disable_cert_verification
        self._tls_clients: Dict[int, Union[None, TLSGatewayClient._TLSGatewayClientProtocol]] = {
            i: None for i in range(self.num_tls_clients)
        }
        self.tls_clients = []

        self.io_tasks = []
        self.io_tasks_funcs = []
        self.tls_client_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue(500)
        self.tls_client_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue(500)
        self._stream_id = 0

    @property
    def tls_client(self):
        if self.tls_clients:
            tls_client_index = self.tls_clients.pop(0)
            self.tls_clients.append(tls_client_index)
            return self._tls_clients[tls_client_index]

    async def run(self):
        self.io_tasks_funcs = [self.tx_message_dispatcher, self.rx_message_dispatcher]
        for index in range(self.num_tls_clients):
            asyncio.ensure_future(self.init_tls_client(index))
        await self.start_io_tasks()

    async def init_tls_client(self, index: int):
        logger.info(f"Starting TLS client {index}, server = ({self.tls_server_host}:{self.tls_server_port})")

        while True:
            try:
                loop = asyncio.get_event_loop()
                tls_client = self._TLSGatewayClientProtocol(index, self.tls_client_read_queue,
                                                            self.tls_client_write_queue)

                # Create an SSL context for TLS 1.3
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                ssl_context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_TLSv1_2
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
                ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

                if self.disable_cert_verification:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                try:
                    transport, protocol = await loop.create_connection(
                        lambda: tls_client,
                        self.tls_server_host, self.tls_server_port,
                        ssl=ssl_context
                    )
                    self._tls_clients[index] = tls_client
                    self.tls_clients.append(index)
                    logger.info(f"TLS client {index} connected")
                    await tls_client.wait_closed
                    logger.error(f"TLS client {index} disconnected, retrying after 1 second")
                    self.tls_clients.remove(index)
                    self._tls_clients[index] = None
                    transport.close()
                    # self.cancel_io_tasks()

                except asyncio.CancelledError:
                    ...

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Unable to connect TLS client {index}, retrying after 5 seconds.")
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
            tls_client = self.tls_client
            if tls_client:
                try:
                    stream_id, payload = self._get_next_available_stream_id(), b"DUMMY DATA"
                    logger.debug(f"TX Dispatcher - {stream_id}: {payload.decode()}")
                    await tls_client.send_data(stream_id, payload)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error("TX Dispatcher error")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no TLS client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        """
        Handle response from TLS server. To be overridden by subclasses.
        :return:
        """
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.tls_client_read_queue.get()
                logger.debug(f"RX Dispatcher - {stream_id}: {repr(data.decode())}")
            except Exception as e:
                logger.error("RX Dispatcher error")
                logger.exception(e)


class TLSGatewayServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.tls_server_read_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.tls_server_write_queue: asyncio.Queue[Tuple[int, bytes]] = asyncio.Queue()
        self.transport = None
        self.tls_writer_task = None
        self.tx_task = None
        self.rx_task = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info("TLS connection established with client")
        asyncio.ensure_future(self.init_tasks())

    def data_received(self, data):
        stream_id = int(struct.unpack('!H', data[:2])[0])
        data = data[2:]
        logger.debug(f"Received from client-proxy, payload: '{repr(data)}' on stream '{stream_id}'")
        asyncio.ensure_future(self.tls_server_read_queue.put((stream_id, data)))

    def connection_lost(self, exc):
        logger.warning("TLS connection lost with client")
        if exc:
            logger.error(f"Connection lost due to {exc}")

    async def init_tasks(self):
        self.tls_writer_task = asyncio.create_task(self.tls_writer())
        self.tx_task = asyncio.create_task(self.tx_message_dispatcher())
        self.rx_task = asyncio.create_task(self.rx_message_dispatcher())
        await asyncio.gather(self.tls_writer_task, self.tx_task, self.rx_task)

    async def send_data(self, stream_id, payload: bytes):
        await self.tls_server_write_queue.put((stream_id, payload))

    async def get_data(self):
        data = await self.tls_server_read_queue.get()
        return data

    async def tls_writer(self):
        while True:
            stream_id, payload = await self.tls_server_write_queue.get()
            logger.debug(f"Sending to client-proxy, payload: '{repr(payload)}' over stream '{stream_id}'")
            self.transport.write(struct.pack('!H', stream_id) + payload)

    async def tx_message_dispatcher(self):
        """
        Sends data to TLS gateway client. To be overridden by subclasses.
        :return:
        """
        logger.info("TX Dispatcher started")

    async def rx_message_dispatcher(self):
        """
        Handle response from TLS client. To be overridden by subclasses.
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


async def init_tls_server(tls_server_host, tls_server_port, certfile, keyfile, disable_cert_verification,
                          server_protocol):
    logger.info(f"Starting TLS server ({tls_server_host}:{tls_server_port})")

    loop = asyncio.get_event_loop()

    # Create SSL context with TLS 1.3
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_TLSv1_2
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
    ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
    ssl_context.load_cert_chain(certfile, keyfile)

    if disable_cert_verification:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    server = await loop.create_server(
        lambda: server_protocol(),
        tls_server_host, tls_server_port,
        ssl=ssl_context
    )

    async with server:
        await server.serve_forever()
