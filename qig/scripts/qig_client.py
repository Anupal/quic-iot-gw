import asyncio

from qig.gateway import IoTGatewayClient
from qig.context import CoAPClientContext, MQTTSNGWClientContext


async def asyncio_main():
    client = IoTGatewayClient(
        quic_server_host="127.0.0.1",
        quic_server_port=4433,
        disable_cert_verification=True,
        coap_context=CoAPClientContext("localhost", 5683),
        mqtt_sn_context=MQTTSNGWClientContext("localhost", 1883),
    )
    await client.run()


def main():
    asyncio.run(asyncio_main())


if __name__ == "__main__":
    main()
