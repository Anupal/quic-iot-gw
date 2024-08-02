import logging
import string
import random
import argparse

import asyncio
import aiocoap.resource as resource
import aiocoap

from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


def process_args():
    parser = argparse.ArgumentParser(description='CoAP server input params')
    parser.add_argument('--message_size_range', type=str, default='50,500',
                        help='Range of message sizes in bytes (e.g., "50,500")')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host address (e.g., "0.0.0.0")')
    parser.add_argument('--port', type=int, default=5684,
                        help='Port number (e.g., 5684)')
    parser.add_argument('--log-level', default='INFO',
                        help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    parser.add_argument('--num-clients', default=500,
                        help='Define the number of coap clients that will connect to the server')

    # Parse arguments
    args = parser.parse_args()

    # Process the message size range
    message_size_range = tuple(map(int, args.message_size_range.split(',')))
    host = args.host
    port = args.port
    log_level = getattr(logging, args.log_level.upper(), logging.WARNING)

    return message_size_range, host, port, log_level, int(args.num_clients)


class CoAPResource(resource.Resource):
    def __init__(self, index=0, message_size_range=(50, 500)):
        super().__init__()
        self.index = index
        self.message_size_range = message_size_range

    async def render_get(self, request):
        logger.debug(f"Received GET request: {request}")
        payload = f"Hello, {self.index} ".encode() + self._generate_bytes(random.randint(*self.message_size_range))
        response = aiocoap.Message(
            payload=payload,
            code=aiocoap.CONTENT
        )
        logger.debug(f"Sending response: {repr(payload)} | {response}")
        return response

    async def render_post(self, request):
        logger.debug(f"Received POST request: {request}")
        payload = f"Hello, {self.index} ".encode()
        response = aiocoap.Message(
            payload=payload,
            code=aiocoap.CHANGED
        )
        logger.debug(f"Sending response: {repr(payload)} | {response}")
        return response

    def _generate_bytes(self, n):
        return "".join(
            [random.choice(string.printable) for _ in range(n)]
        ).encode()


async def coap_server(host, port, num_clients, message_size_range):
    root = resource.Site()

    for i in range(1, num_clients + 1):
        root.add_resource([f"hello{i}"], CoAPResource(i, message_size_range))

    logger.debug(f"root={root.get_resources_as_linkheader()}")

    logger.info(f"Starting CoAP Backend Server ({host}:{port})")
    await aiocoap.Context.create_server_context(root, bind=(host, port))

    # Serve until process is killed
    await asyncio.get_running_loop().create_future()


def start_coap_server():
    message_size_range, host, port, log_level, num_clients = process_args()
    setup_logger(logging_level=log_level)

    logger.info("Starting CoAP Backend Server Process")
    asyncio.run(coap_server(host, port, num_clients, message_size_range))


