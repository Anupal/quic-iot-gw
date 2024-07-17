import logging
from typing import Tuple

import aiocoap
import asyncio
import asyncio_dgram


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


class CoAPClientContext(ClientContext):
    def __init__(self, host, port):
        super().__init__()
        self.host, self.port = host, port
        # self._pending_requests = {}
        self._device_stream_map = {}
        self._stream_device_map = {}

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

    async def handle_read_message(self, get_next_stream_id: callable):
        data, client_address = await self.read_queue.get()
        if client_address in self._device_stream_map:
            stream_id = self._device_stream_map[client_address]
        else:
            stream_id = get_next_stream_id()
            self._device_stream_map[client_address] = stream_id
            self._stream_device_map[stream_id] = client_address

        logger.info(f"Handling CoAP request from {client_address}")
        coap_data = aiocoap.Message.decode(data)
        # self._pending_requests[(coap_data.token, coap_data.mid)] = client_address
        return data, stream_id

    async def handle_write_message(self, data, stream_id):
        logger.info(f"Handling CoAP response")
        coap_data = aiocoap.Message.decode(data)
        logger.info(f"Decoded CoAP response = {coap_data}")
        if stream_id in self._stream_device_map:
        # if (coap_data.token, coap_data.mid) in self._pending_requests:
            # client_address = self._pending_requests.pop((coap_data.token, coap_data.mid))
            client_address = self._stream_device_map[stream_id]
            await self.write_queue.put((data, client_address))

    def is_valid(self, data):
        try:
            message = aiocoap.Message.decode(data)
            # check code type is Unknown if parsing passes
            return "Unknown" not in message.code.name_printable
        except:
            return False

    def reset(self):
        logger.info("Resetting CoAP context - cleared pending requests, stream ids")
        # self._pending_requests = {}
        self._device_stream_map = {}


class ServerContext:
    async def handle_read_message(self, data):
        """
        Read data from read queue and save request information like MID, client address.
        """

    async def handle_write_message(self, data):
        """
        Write to write queue and send it to application protocol io.
        """

    def is_valid(self, data) -> bool:
        ...


class CoAPServerContext(ServerContext):
    async def handle_read_message(self, data):
        coap_request = aiocoap.Message.decode(data)
        if coap_request.opt.proxy_uri is None:
            logger.warning("Proxy-URI option missing in request")
            response = aiocoap.Message(code=aiocoap.BAD_OPTION)
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
                response = aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR)

        response.mid = coap_request.mid
        response.token = coap_request.token
        return response.encode()

    async def handle_write_message(self, data):
        ...

    def is_valid(self, data) -> bool:
        try:
            message = aiocoap.Message.decode(data)
            # check code type is Unknown if parsing passes
            return "Unknown" not in message.code.name_printable
        except:
            return False