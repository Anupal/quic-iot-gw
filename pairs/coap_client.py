import aiocoap
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    protocol = await aiocoap.Context.create_client_context()

    # Define the backend server URI
    backend_uri = 'coap://localhost:5684/hello'
    proxy_uri = 'coap://localhost:5683/proxy'

    while True:
        choice = input("'send' or 'exit'")
        if choice == 'send':
            # Send a GET request through the proxy
            request = aiocoap.Message(code=aiocoap.GET, uri=proxy_uri)
            request.opt.proxy_uri = backend_uri
            logger.info(f"Sending GET request through proxy to {backend_uri}")
            response = await protocol.request(request).response
            logger.info(f"Received GET response: {response.payload.decode('utf-8')}")

            # Send a POST request through the proxy
            payload = b"New content from client"
            request = aiocoap.Message(code=aiocoap.POST, uri=proxy_uri, payload=payload)
            request.opt.proxy_uri = backend_uri
            logger.info(f"Sending POST request through proxy to {backend_uri}")
            response = await protocol.request(request).response
            logger.info(f"Received POST response: {response.payload.decode('utf-8')}")

            # Verify the content after POST through the proxy
            request = aiocoap.Message(code=aiocoap.GET, uri=proxy_uri)
            request.opt.proxy_uri = backend_uri
            logger.info(f"Sending GET request through proxy to verify POST to {backend_uri}")
            response = await protocol.request(request).response
            logger.info(f"Received GET response after POST: {response.payload.decode('utf-8')}")
        elif choice == 'exit':
            break


if __name__ == "__main__":
    asyncio.run(main())
