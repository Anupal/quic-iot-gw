import logging

import asyncio
import argparse
import os
import configparser
from quic_iot_gateway.gateway import IoTGatewayClient
from quic_iot_gateway.context import CoAPClientContext, MQTTSNGWClientContext
from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


async def asyncio_main(quic_server_host, quic_server_port, disable_cert_verification, coap_host, coap_port, mqtt_sn_host, mqtt_sn_port):
    client = IoTGatewayClient(
        quic_server_host=quic_server_host,
        quic_server_port=quic_server_port,
        disable_cert_verification=disable_cert_verification,
        coap_context=CoAPClientContext(coap_host, coap_port),
        mqtt_sn_context=MQTTSNGWClientContext(mqtt_sn_host, mqtt_sn_port),
    )
    await client.run()


def main():
    parser = argparse.ArgumentParser(description="IoT Gateway Client Configuration")
    parser.add_argument('--config', type=str, help='Path to the configuration INI file')
    parser.add_argument('--quic_server_host', type=str, help='QUIC server host')
    parser.add_argument('--quic_server_port', type=int, help='QUIC server port')
    parser.add_argument('--disable_cert_verification', action='store_true', help='Disable certificate verification')
    parser.add_argument('--coap_host', type=str, help='CoAP host')
    parser.add_argument('--coap_port', type=int, help='CoAP port')
    parser.add_argument('--mqtt_sn_host', type=str, help='MQTT-SN gateway host')
    parser.add_argument('--mqtt_sn_port', type=int, help='MQTT-SN gateway port')
    parser.add_argument('--log-level', default='WARNING',
                        help='Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper(), logging.WARNING)
    setup_logger(log_level)

    config = configparser.ConfigParser()
    if args.config:
        if not os.path.exists(args.config):
            logger.error(f"Configuration file {args.config} does not exist.")
            return
        config.read(args.config)

    quic_server_host = args.quic_server_host or config.get('quic_server', 'host', fallback='127.0.0.1')
    quic_server_port = args.quic_server_port or config.getint('quic_server', 'port', fallback=4433)
    disable_cert_verification = args.disable_cert_verification or config.getboolean('quic_server', 'disable_cert_verification', fallback=True)
    coap_host = args.coap_host or config.get('coap', 'host', fallback='localhost')
    coap_port = args.coap_port or config.getint('coap', 'port', fallback=5683)
    mqtt_sn_host = args.mqtt_sn_host or config.get('mqtt_sn', 'host', fallback='localhost')
    mqtt_sn_port = args.mqtt_sn_port or config.getint('mqtt_sn', 'port', fallback=1883)

    asyncio.run(asyncio_main(quic_server_host, quic_server_port, disable_cert_verification, coap_host, coap_port, mqtt_sn_host, mqtt_sn_port))


if __name__ == "__main__":
    main()
