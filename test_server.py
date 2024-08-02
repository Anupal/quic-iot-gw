import asyncio
import logging

from quic_iot_gateway.tls.transport import init_tls_server, TLSGatewayServerProtocol

from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


async def async_main():
    server = await init_tls_server(
        "0.0.0.0",
        1234,
        "tests/certs/cert.pem",
        "tests/certs/key.pem",
        True,
        TLSGatewayServerProtocol)
    async with server:
        await server.serve_forever()
    # await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    setup_logger(logging_level=logging.DEBUG)
    asyncio.run(async_main())
