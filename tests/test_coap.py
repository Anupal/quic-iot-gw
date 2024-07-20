import logging
import string
import random
import time

import asyncio
import aiocoap.resource as resource
import aiocoap
import multiprocessing as mp

from quic_iot_gateway.utils import setup_logger

setup_logger(logging_level=logging.WARNING)
logger = logging.getLogger(__name__)

BACKEND_URI = 'coap://localhost:5684/hello'
PROXY_URI = 'coap://localhost:5683/proxy'
NUM_CLIENTS = 500
REQUESTS = 50
MESSAGE_SIZE_RANGE = (50, 500)  # bytes
STARTING_PORT = 30001


def generate_bytes(n):
    return "".join(
        [random.choice(string.printable) for _ in range(n)]
    ).encode()


class CoAPResource(resource.Resource):
    def __init__(self, index=0):
        super().__init__()
        self.index = index

    async def render_get(self, request):
        logger.info(f"Received GET request: {request}")
        payload = f"Hello, {self.index} ".encode() + generate_bytes(random.randint(*MESSAGE_SIZE_RANGE))
        response = aiocoap.Message(
            payload=payload,
            code=aiocoap.CONTENT
        )
        logger.info(f"Sending response: {repr(payload)} | {response}")
        return response

    async def render_post(self, request):
        logger.info(f"Received POST request: {request}")
        payload = f"Hello, {self.index} ".encode() + request.payload
        response = aiocoap.Message(
            payload=payload,
            code=aiocoap.CHANGED
        )
        logger.info(f"Sending response: {repr(payload)} | {response}")
        return response


async def coap_server(num_clients):
    root = resource.Site()

    for i in range(1, num_clients + 1):
        root.add_resource([f"hello{i}"], CoAPResource(i))

    logger.info(f"root={root.get_resources_as_linkheader()}")

    logger.info("Starting CoAP Backend Server")
    await aiocoap.Context.create_server_context(root, bind=("0.0.0.0", 5684))

    # Serve until process is killed
    await asyncio.get_running_loop().create_future()


def start_coap_server(num_clients):
    logger.info("Starting CoAP Backend Server Process")
    asyncio.run(coap_server(num_clients))


async def coap_client(index):
    protocol = await aiocoap.Context.create_server_context(resource.Site(), bind=("0.0.0.0", STARTING_PORT + index))
    resource_uri = BACKEND_URI + f"{index}"

    success = 0
    for _ in range(REQUESTS):
        get_post = random.randint(0, 1)
        time.sleep(random.random() + random.random())
        if get_post == 0:
            logger.info(f"Sending GET request through proxy {PROXY_URI} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.GET, uri=PROXY_URI)
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
            logger.info(f"Sending POST request through proxy {PROXY_URI} to {resource_uri}")
            request = aiocoap.Message(code=aiocoap.POST, uri=PROXY_URI,
                                      payload=generate_bytes(random.randint(*MESSAGE_SIZE_RANGE))
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


def start_coap_client(index, results: mp.Queue):
    result = asyncio.run(coap_client(index))
    results.put((index, result))


def main():
    results = mp.Queue()

    p_coap_server = mp.Process(target=start_coap_server, args=(NUM_CLIENTS,), daemon=True)
    p_coap_clients = [
        mp.Process(target=start_coap_client, args=(i, results), daemon=True)
        for i in range(1, NUM_CLIENTS + 1)
    ]
    p_coap_server.start()

    time.sleep(1)
    logger.info(f"Starting CoAP Clients...")
    for client in p_coap_clients:
        client.start()

    while results.qsize() != NUM_CLIENTS: ...

    table = []
    logger.warning("Retrieving results:")
    for i in range(NUM_CLIENTS):
        table.append(results.get())

    for client in p_coap_clients:
        client.join()
    p_coap_server.kill()

    table.sort(key=lambda x: x[0])
    for index, result in table:
        logger.warning(f"| {index:<5} | {result:<5} |")


if __name__ == "__main__":
    main()
