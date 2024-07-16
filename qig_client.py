import asyncio

from gateway import IoTGatewayClient, CoAPClientContext


async def main():
    client = IoTGatewayClient(
        quic_server_host="127.0.0.1",
        quic_server_port=4433,
        disable_cert_verification=True,
        coap_context=CoAPClientContext("localhost", 5683)
    )
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
