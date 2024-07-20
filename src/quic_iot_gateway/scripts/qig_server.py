import logging

import asyncio
import argparse
import os
import configparser
from quic_iot_gateway.transport import init_quic_server
from quic_iot_gateway.context import CoAPServerContext, MQTTSNGWServerContext
from quic_iot_gateway.gateway import iot_gateway_server_protocol_factory
from quic_iot_gateway.utils import setup_logger

logger = logging.getLogger(__name__)


async def asyncio_main(quic_server_host, quic_server_port, cert_file, key_file, disable_cert_verification, mqtt_broker_host, mqtt_broker_port):
    await init_quic_server(
        quic_server_host,
        quic_server_port,
        cert_file,
        key_file,
        disable_cert_verification,
        iot_gateway_server_protocol_factory(
            coap_context=CoAPServerContext(),
            mqtt_sn_context=MQTTSNGWServerContext(mqtt_broker_host, mqtt_broker_port)
        ),
    )
    # Keep the server running
    await asyncio.get_running_loop().create_future()


def main():
    parser = argparse.ArgumentParser(description="IoT Gateway Server Configuration")
    parser.add_argument('--config', type=str, help='Path to the configuration INI file')
    parser.add_argument('--quic_server_host', type=str, help='QUIC server host')
    parser.add_argument('--quic_server_port', type=int, help='QUIC server port')
    parser.add_argument('--cert_file', type=str, help='Path to the certificate file')
    parser.add_argument('--key_file', type=str, help='Path to the key file')
    parser.add_argument('--disable_cert_verification', action='store_true', help='Disable certificate verification')
    parser.add_argument('--mqtt_broker_host', type=str, help='MQTT-SN gateway host')
    parser.add_argument('--mqtt_broker_port', type=int, help='MQTT-SN gateway port')
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
    cert_file = args.cert_file or config.get('quic_server', 'cert_file', fallback='cert.pem')
    key_file = args.key_file or config.get('quic_server', 'key_file', fallback='key.pem')
    disable_cert_verification = args.disable_cert_verification or config.getboolean('quic_server', 'disable_cert_verification', fallback=True)
    mqtt_broker_host = args.mqtt_broker_host or config.get('mqtt_broker', 'host', fallback='localhost')
    mqtt_broker_port = args.mqtt_broker_port or config.getint('mqtt_broker', 'port', fallback=1883)

    # Check if cert_file and key_file exist
    if not disable_cert_verification:
        if not cert_file or not os.path.exists(cert_file):
            logger.error(f"Certificate file {cert_file} does not exist.")
            return
        if not key_file or not os.path.exists(key_file):
            logger.error(f"Key file {key_file} does not exist.")
            return

    asyncio.run(asyncio_main(quic_server_host, quic_server_port, cert_file, key_file, disable_cert_verification, mqtt_broker_host, mqtt_broker_port))


if __name__ == "__main__":
    main()
