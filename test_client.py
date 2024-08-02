import asyncio
import logging

from quic_iot_gateway.tls.transport import TLSGatewayClient

from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


async def async_main():
    client = TLSGatewayClient(
        'localhost',
        1234,
        10,
        True
    )
    await client.run()


if __name__ == "__main__":
    setup_logger(logging_level=logging.DEBUG)
    asyncio.run(async_main())
