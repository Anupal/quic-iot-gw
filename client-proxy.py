import asyncio
import coap

asyncio.run(coap.proxy.run_client_proxy(
    "localhost", 4433, "localhost", 5683, True
))
