import asyncio
import logging

from aioquic.asyncio import connect, serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, StreamDataReceived


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProxyClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._next_stream_id = 0  # Start with 0 for client-initiated streams
        self.responses = asyncio.Queue()

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            logger.info("QUIC handshake completed")
            self._stream_id = self._quic.get_next_available_stream_id()

        elif isinstance(event, StreamDataReceived):
            logger.info(f"Received: {event.data} on stream {event.stream_id}")
            asyncio.ensure_future(self.responses.put(event.data))

    async def send_request_over_quic(self, payload):
        logger.info(f"Sending to server-proxy, payload: '{payload}'")
        self._quic.send_stream_data(self._stream_id, payload)
        self.transmit()

        response = await self.responses.get()
        return response


class ProxyServerProtocol(QuicConnectionProtocol):
    packet_handler = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stream_id = None

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            self._stream_id = self._quic.get_next_available_stream_id()

        elif isinstance(event, StreamDataReceived):
            asyncio.ensure_future(self.handle_quic_request(event.data, event.stream_id))

    async def handle_quic_request(self, data, stream_id):
        logger.info(f"Received data over QUIC: {data}")

        response = await ProxyServerProtocol.packet_handler(data)

        # Send the CoAP response back over QUIC
        self._quic.send_stream_data(stream_id, response.encode())
        self.transmit()


def get_quic_client(quic_server_host, quic_server_port, disable_cert_verification=True):
    logger.info(f"Starting QUIC transport client, remote server = ({quic_server_host}:{quic_server_port})")
    configuration = QuicConfiguration(is_client=True)
    configuration.verify_mode = not disable_cert_verification  # Disable certificate verification for testing

    return connect(quic_server_host, quic_server_port, configuration=configuration,
                       create_protocol=ProxyClientProtocol)


async def get_quic_server(quic_server_host, quic_server_port, certfile, keyfile):
    logger.info(f"Starting QUIC transport server ({quic_server_host}:{quic_server_port})")
    configuration = QuicConfiguration(is_client=False)
    configuration.load_cert_chain(certfile=certfile, keyfile=keyfile)

    return await serve(quic_server_host, quic_server_port, configuration=configuration, create_protocol=ProxyServerProtocol)
