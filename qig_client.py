import asyncio

from gateway import IoTGatewayClient
from context import CoAPClientContext, MQTTSNGWClientContext


async def main():
    client = IoTGatewayClient(
        quic_server_host="127.0.0.1",
        quic_server_port=4433,
        disable_cert_verification=True,
        coap_context=CoAPClientContext("localhost", 5683),
        mqtt_sn_context=MQTTSNGWClientContext("localhost", 1883),
    )
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
