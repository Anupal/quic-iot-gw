import asyncio

from transport import init_quic_server
from gateway import IoTGatewayServerProtocol


async def main():
    await init_quic_server(
        "127.0.0.1",
        4433,
        "cert.pem",
        "key.pem",
        True,
        IoTGatewayServerProtocol
    )
    # Keep the server running
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
