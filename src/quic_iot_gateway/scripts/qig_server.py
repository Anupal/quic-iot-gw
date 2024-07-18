import asyncio

from qig.transport import init_quic_server
from qig.context import CoAPServerContext, MQTTSNGWServerContext
from qig.gateway import iot_gateway_server_protocol_factory


async def asyncio_main():
    await init_quic_server(
        "127.0.0.1",
        4433,
        "cert.pem",
        "key.pem",
        True,
        iot_gateway_server_protocol_factory(
            coap_context=CoAPServerContext(),
            mqtt_sn_context=MQTTSNGWServerContext("localhost", 1883)
        ),
    )
    # Keep the server running
    await asyncio.get_running_loop().create_future()


def main():
    asyncio.run(asyncio_main())


if __name__ == "__main__":
    main()
