import logging

import aiocoap
import asyncio
import asyncio_dgram

import transport
from iot_protocols import CoAPServerContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# todo: figure out bidirectional flow


class IoTGatewayClient(transport.QUICGatewayClient):
    def __init__(self, *args, coap_context, **kwargs):
        super().__init__(*args, **kwargs)

        self.coap_context = coap_context
        asyncio.ensure_future(coap_context.run())

    async def run(self):
        self.io_tasks = []
        self.io_tasks_funcs = [self.coap_tx_message_dispatcher, self.rx_message_dispatcher]

        await self.init_quic_client()

    async def coap_tx_message_dispatcher(self):
        logger.info("CoAP TX Dispatcher started")
        self.coap_context.reset()
        while True:
            if self.quic_client:
                try:
                    payload, stream_id = await self.coap_context.handle_read_message(
                        self.quic_client._quic.get_next_available_stream_id
                    )

                    logger.info(f"TX Dispatcher - {stream_id}: {payload}")
                    await self.quic_client.send_data(stream_id, payload)

                except Exception as e:
                    logger.error("TX Dispatcher - Error occurred when handling CoAP message...")
                    logger.exception(e)
            else:
                logger.error("TX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)

    async def rx_message_dispatcher(self):
        logger.info("RX Dispatcher started")
        while True:
            if self.quic_client:
                try:
                    stream_id, data = await self.quic_client.get_data()
                    logger.info(f"RX Dispatcher - {stream_id}: {data}")
                    if self.coap_context.is_valid(data):
                        await self.coap_context.handle_write_message(data, stream_id)
                except Exception as e:
                    logger.error("RX Dispatcher - Error occurred when handling CoAP message...")
                    logger.exception(e)
            else:
                logger.error("RX Dispatcher - no quic client available, retrying after 5 seconds.")
                await asyncio.sleep(5)


class IoTGatewayServerProtocol(transport.QUICGatewayServerProtocol):
    async def tx_message_dispatcher(self):
        logger.info("TX Dispatcher started")

    async def rx_message_dispatcher(self):
        coap_context = CoAPServerContext()
        logger.info("RX Dispatcher started")
        while True:
            try:
                stream_id, data = await self.get_data()
                logger.info(f"RX Dispatcher - {stream_id}: {data}")

                if coap_context.is_valid(data):
                    response = await coap_context.handle_read_message(data)
                    await self.send_data(stream_id, response)
            except Exception as e:
                logger.error("RX Dispatcher - error in received data...")
                logger.exception(e)
