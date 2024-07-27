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

aiocoap_logger = logging.getLogger('aiocoap.messagemanager')
aiocoap_logger.setLevel(logging.CRITICAL)


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
    parser.add_argument('--req-type', default="mixed",
                        help="Define the type of request: 'post', 'get', 'mixed")
    parser.add_argument('--loops', default=1,
                        help='Define number of times to run the test.')

    # Parse arguments
    args = parser.parse_args()

    # Process the message size range
    message_size_range = tuple(map(int, args.message_size_range.split(',')))
    coap_server_host = args.coap_server_host
    coap_server_port = int(args.coap_server_port)
    coap_proxy_host = args.coap_proxy_host
    coap_proxy_port = int(args.coap_proxy_port)
    loops = int(args.loops)

    log_level = getattr(logging, args.log_level.upper(), logging.WARNING)
    req_type = args.req_type

    return (
        message_size_range,
        f"coap://{coap_server_host}:{coap_server_port}/hello",
        f"coap://{coap_proxy_host}:{coap_proxy_port}/proxy",
        log_level, int(args.num_clients), int(args.num_requests), int(args.starting_port), req_type, loops
    )


async def coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port, req_type="mixed"):
    protocol = await aiocoap.Context.create_server_context(resource.Site(), bind=("0.0.0.0", starting_port + index))
    resource_uri = backend_uri + f"{index}"

    success = 0
    times = []
    for _ in range(num_requests):
        if req_type == "mixed":
            get_post = random.randint(0, 1)
        elif req_type == "get":
            get_post = 0
        else:
            get_post = 1

        time.sleep(random.random()) # + random.random())
        if get_post == 0:
            logger.debug(f"Sending GET request through proxy {proxy_uri} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.GET, uri=proxy_uri)
            request.opt.proxy_uri = resource_uri
            try:
                start = time.time()
                response = await protocol.request(request).response
                end = time.time()
                logger.debug(
                    f"Received GET response: code='{response.code}' payload='{repr(response.payload)}'")
                if response.code == aiocoap.CONTENT and f"Hello, {index} ".encode() in response.payload:
                    times.append(end - start)
                    success += 1
            except Exception as e:
                logger.error("Error sending GET request", exc_info=e)
        else:
            logger.debug(f"Sending POST request through proxy {proxy_uri} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.POST, uri=proxy_uri,
                                      payload=generate_bytes(random.randint(*message_size_range))
                                      )
            request.opt.proxy_uri = resource_uri
            try:
                start = time.time()
                response = await protocol.request(request).response
                end = time.time()
                logger.debug(
                    f"Received POST response: code='{response.code}' payload='{repr(response.payload)}'")
                if response.code == aiocoap.CHANGED and f"Hello, {index} ".encode() in response.payload:
                    times.append(end - start)
                    success += 1
            except Exception as e:
                logger.error("Error sending POST request", exc_info=e)
    await protocol.shutdown()
    if times:
        average_time_taken = sum(times) / len(times)
    else:
        average_time_taken = None
    return success, average_time_taken


def start_coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port, req_type,
                      results: mp.Queue):
    success, average_time_taken = asyncio.run(coap_client(index, backend_uri, proxy_uri, num_requests, message_size_range, starting_port,
                                     req_type))
    results.put((index, success, average_time_taken))


def main():
    message_size_range, backend_uri, proxy_uri, log_level, num_clients, num_requests, starting_port, req_type, loops = process_args()
    setup_logger(logging_level=log_level)

    for _ in range(loops):
        results = mp.Queue()
        p_coap_clients = [
            mp.Process(target=start_coap_client, args=(i, backend_uri, proxy_uri, num_requests, message_size_range,
                                                       starting_port, req_type, results), daemon=True)
            for i in range(1, num_clients + 1)
        ]

        if loops > 1:
            logger.info("Sleeping for 1 second...")
            time.sleep(1)
        logger.info(f"Starting CoAP Clients...")
        for client in p_coap_clients:
            client.start()

        while results.qsize() != num_clients: ...

        table = []
        logger.info("Retrieving results:")
        for i in range(num_clients):
            res = results.get()
            if res[2]:
                table.append(res)

        for client in p_coap_clients:
            client.join()

        table.sort(key=lambda x: x[0])
        for index, success, time_taken in table:
            logger.debug(f"| {index:<5} | {success:<5} | {time_taken:<5} |")

        logger.critical("Result")
        logger.critical(f"Successful requests: {sum([res[1] for res in table]) / num_clients:.2f}")
        logger.critical(f"Average time taken (s): {sum([res[2] for res in table]) / num_clients:.4f}")
