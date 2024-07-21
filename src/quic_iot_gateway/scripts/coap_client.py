import argparse
import logging
import string
import random
import time

import asyncio
import aiocoap.resource as resource
import aiocoap
import multiprocessing as mp

from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


def generate_bytes(n):
    return "".join(
        [random.choice(string.printable) for _ in range(n)]
    ).encode()


def process_args():
    parser = argparse.ArgumentParser(description='CoAP client input params')
    parser.add_argument('--message_size_range', type=str, default='50,500',
                        help='Range of message sizes in bytes (e.g., "50,500")')
    parser.add_argument('--coap-server-host', type=str, default='localhost',
                        help='Host address (e.g., "localhost)')
    parser.add_argument('--coap-server-port', type=int, default=5684,
                        help='Port number (e.g., 5684)')
    parser.add_argument('--coap-proxy-host', type=str, default='localhost',
                        help='Host address (e.g., "localhost)')
    parser.add_argument('--coap-proxy-port', type=int, default=5683,
                        help='Port number (e.g., 5683)')
    parser.add_argument('--log-level', default='INFO',
                        help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    parser.add_argument('--num-clients', default=500,
                        help='Define the number of coap clients that will connect to the server')
    parser.add_argument('--num-requests', default=50,
                        help='Define the number of requests made per coap client.')
    parser.add_argument('--starting-port', default=30001,
                        help='Define the starting port number to be used by coap clients.')

    # Parse arguments
    args = parser.parse_args()

    # Process the message size range
    message_size_range = tuple(map(int, args.message_size_range.split(',')))
    coap_server_host = args.coap_server_host
    coap_server_port = int(args.coap_server_port)
    coap_proxy_host = args.coap_proxy_host
    coap_proxy_port = int(args.coap_proxy_port)
    log_level = getattr(logging, args.log_level.upper(), logging.WARNING)

    return (
        message_size_range,
        f"coap://{coap_server_host}:{coap_server_port}/hello",
        f"coap://{coap_proxy_host}:{coap_proxy_port}/proxy",
        log_level, int(args.num_clients), int(args.num_requests), int(args.starting_port)
    )


async def coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port):
    protocol = await aiocoap.Context.create_server_context(resource.Site(), bind=("0.0.0.0", starting_port + index))
    resource_uri = backend_uri + f"{index}"

    success = 0
    for _ in range(num_requests):
        get_post = random.randint(0, 1)
        time.sleep(random.random() + random.random())
        if get_post == 0:
            logger.info(f"Sending GET request through proxy {proxy_uri} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.GET, uri=proxy_uri)
            request.opt.proxy_uri = resource_uri
            try:
                response = await protocol.request(request).response
                logger.info(
                    f"Received GET response: code='{response.code}' payload='{response.payload.decode()}'")
                if response.code == aiocoap.CONTENT and f"Hello, {index} " in response.payload.decode():
                    success += 1
            except Exception as e:
                logger.error("Error sending GET request", exc_info=e)
        else:
            logger.info(f"Sending POST request through proxy {proxy_uri} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.POST, uri=proxy_uri,
                                      payload=generate_bytes(random.randint(*message_size_range))
                                      )
            request.opt.proxy_uri = resource_uri
            try:
                response = await protocol.request(request).response
                logger.info(
                    f"Received POST response: code='{response.code}' payload='{response.payload.decode()}'")
                if response.code == aiocoap.CHANGED and f"Hello, {index} " in response.payload.decode():
                    success += 1
            except Exception as e:
                logger.error("Error sending POST request", exc_info=e)
    await protocol.shutdown()
    return success


def start_coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port, results: mp.Queue):
    result = asyncio.run(coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port))
    results.put((index, result))


def main():
    message_size_range, backend_uri, proxy_uri, log_level, num_clients, num_requests, starting_port = process_args()
    setup_logger(logging_level=log_level)

    while True:
        results = mp.Queue()
        p_coap_clients = [
            mp.Process(target=start_coap_client, args=(i, backend_uri, proxy_uri, num_requests, message_size_range,
                                                       starting_port, results), daemon=True)
            for i in range(1, num_clients + 1)
        ]

        logger.warning("Sleeping for 5 seconds...")
        time.sleep(5)
        logger.warning(f"Starting CoAP Clients...")
        for client in p_coap_clients:
            client.start()

        while results.qsize() != num_clients: ...

        table = []
        logger.warning("Retrieving results:")
        for i in range(num_clients):
            table.append(results.get())

        for client in p_coap_clients:
            client.join()

        table.sort(key=lambda x: x[0])
        for index, result in table:
            logger.info(f"| {index:<5} | {result:<5} |")

        logger.warning(f"Result: {sum([res[1] for res in table]) / num_clients:.2f}")
