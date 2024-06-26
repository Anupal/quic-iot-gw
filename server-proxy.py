import asyncio
import coap

asyncio.run(coap.proxy.run_server_proxy(
    "localhost", 4433, "cert.pem", "key.pem"
))
