import logging

import asyncio

import quic_iot_gateway.tcp.transport as transport

logger = logging.getLogger(__name__)


class IoTGatewayClient(transport.TCPGatewayClient):
    def __init__(self, *args, coap_context, mqtt_sn_context, **kwargs):
        super().__init__(*args, **kwargs)

        self.coap_context = coap_context
        self.mqtt_sn_context = mqtt_sn_context
        asyncio.ensure_future(coap_context.run())
        asyncio.ensure_future(mqtt_sn_context.run())

    async def run(self):
        self.io_tasks = []
        self.io_tasks_funcs = [
            self.coap_tx_message_dispatcher,
            self.mqtt_sn_tx_message_dispatcher,
            self.rx_message_dispatcher
        ]

        await self.init_tcp_client()

    async def mqtt_sn_tx_message_dispatcher(self):
        logger.info("MQTT-SN TX Dispatcher started")
        self.mqtt_sn_context.reset()
        while True:
            if self.tcp_client:
                try:
                    ret = await self.mqtt_sn_context.handle_read_message(
                        self._get_next_available_stream_id
                    )
                    # If there is data to be forwarded
                    if ret:
                        payload, stream_id = ret
                        logger.debug(f"TX Dispatcher - {stream_id}: {repr(payload)}")
                        await self.tcp_client.send_data(stream_id, payload)

                except Exception as e:
                    logger.error("TX Dispatcher - Error occurred when handling MQTT-SN message...")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no TCP client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def coap_tx_message_dispatcher(self):
        logger.info("CoAP TX Dispatcher started")
        self.coap_context.reset()
        while True:
            if self.tcp_client:
                try:
                    payload, stream_id = await self.coap_context.handle_read_message(
                        self._get_next_available_stream_id
                    )

                    logger.debug(f"TX Dispatcher - {stream_id}: {repr(payload)}")
                    await self.tcp_client.send_data(stream_id, payload)

                except Exception as e:
                    logger.error("TX Dispatcher - Error occurred when handling CoAP message...")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        logger.info("RX Dispatcher started")
        while True:
            if self.tcp_client:
                try:
                    stream_id, data = await self.tcp_client.get_data()
                    logger.debug(f"RX Dispatcher - {stream_id}: {repr(data)}")
                    if self.coap_context.is_valid(data):
                        await self.coap_context.handle_write_message(data, stream_id)
                    if self.mqtt_sn_context.is_valid(data):
                        await self.mqtt_sn_context.handle_write_message(data, stream_id)

                except Exception as e:
                    logger.error("RX Dispatcher - Error occurred when handling message received from server-proxy...")
                    logger.exception(e)
            else:
                logger.error("RX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)


class IoTGatewayServerProtocolTemplate(transport.TCPGatewayServerProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def tx_message_dispatcher(self):
        logger.info("TX Dispatcher started")

    async def rx_message_dispatcher(self):
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.get_data()
                logger.debug(f"RX Dispatcher - {stream_id}: {repr(data)}")

                if self.coap_context.is_valid(data):
                    response = await self.coap_context.handle_write_message(data)
                    if response:
                        await self.send_data(stream_id, response)

                if self.mqtt_sn_context.is_valid(data):
                    response = await self.mqtt_sn_context.handle_write_message(data)
                    if response:
                        await self.send_data(stream_id, response)

            except Exception as e:
                logger.error("RX Dispatcher - error in received data...")
                logger.exception(e)


def iot_gateway_server_protocol_factory(coap_context, mqtt_sn_context, **kwargs):
    asyncio.ensure_future(coap_context.run())
    asyncio.ensure_future(mqtt_sn_context.run())
    return type(
        'IoTGatewayServerProtocol',
        (IoTGatewayServerProtocolTemplate,),
        {
            'coap_context': coap_context,
            'mqtt_sn_context': mqtt_sn_context,
            **kwargs
        }
    )
