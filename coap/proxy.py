import asyncio
import logging

import aiocoap.resource as resource
import aiocoap

import coap.transport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoAPProxyResource(resource.Resource):
    def __init__(self, quic_client):
        super().__init__()
        self.quic_client = quic_client

    async def render_get(self, request):
        return await self.__proxy_request(request)

    async def render_post(self, request):
        return await self.__proxy_request(request)

    async def __proxy_request(self, request):
        if request.opt.proxy_uri is None:
            logger.warning("Proxy-URI option missing in request")
            return aiocoap.Message(code=aiocoap.BAD_OPTION)

        logger.info(f"Encapsulating request as QUIC payload and sending to server-proxy")

        # Send request over QUIC
        response_payload = await self.quic_client.send_request_over_quic(request.encode())

        logger.info("Decoding CoAP response received over QUIC")
        response = aiocoap.Message.decode(response_payload)

        return response


async def coap_packet_handler(data):
    try:
        coap_request = aiocoap.Message.decode(data)
        logger.info(f"Decoded CoAP request: {coap_request}")
    except Exception as e:
        logger.error(f"Failed to decode CoAP message: {e}")
        return

    if coap_request.opt.proxy_uri is None:
        logger.warning("Proxy-URI option missing in request")
        response = aiocoap.Message(code=aiocoap.BAD_OPTION)
    else:
        target_uri = coap_request.opt.proxy_uri
        logger.info(f"Proxying request to {target_uri}")

        # Forward the CoAP request to the actual server
        protocol = await aiocoap.Context.create_client_context()
        proxy_request = aiocoap.Message(code=coap_request.code, uri=target_uri, payload=coap_request.payload)

        try:
            coap_response = await protocol.request(proxy_request).response
            logger.info(f"Forwarded request to {target_uri}, received response: {coap_response} payload: "
                        f"'{coap_response.payload}'")
            coap_response.opt.proxy_uri = coap_response.opt.proxy_uri
            response = coap_response
        except Exception as e:
            logger.error(f"Failed to get response from server: {e}")
            response = aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR)

    return response


async def run_client_proxy(quic_server_host: str, quic_server_port: int, coap_proxy_host: str, coap_proxy_port: int,
                           disable_cert_verification: bool = False):
    async with coap.transport.get_quic_client(quic_server_host, quic_server_port,
                                              disable_cert_verification) as quic_client:
        logger.info(f"QUIC transport client connected, {quic_client}")

        # Set up CoAP server with QUIC integration
        root = resource.Site()
        coap_proxy_resource = CoAPProxyResource(quic_client)
        root.add_resource(['proxy'], coap_proxy_resource)

        logger.info(f"Starting CoAP Proxy Server ({coap_proxy_host}:{coap_proxy_port})")
        await aiocoap.Context.create_server_context(root, bind=(coap_proxy_host, coap_proxy_port))

        # Serve until process is killed
        await asyncio.get_running_loop().create_future()


async def run_server_proxy(quic_server_host, quic_server_port, certfile, keyfile):
    logger.info(f"Starting QUIC server ({quic_server_host}:{quic_server_port})")
    quic_server = await coap.transport.get_quic_server(quic_server_host, quic_server_port, certfile, keyfile)
    quic_server._create_protocol.packet_handler = coap_packet_handler

    # Serve until process is killed
    await asyncio.get_running_loop().create_future()
