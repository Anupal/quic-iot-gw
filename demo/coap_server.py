import asyncio
import json

import aiocoap
import aiocoap.resource as resource
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


sensor_data = {}


class CoAPResource(resource.Resource):
    def __init__(self):
        super().__init__()

    async def render_post(self, request):
        try:
            data = json.loads(request.payload.decode())

            sensor_id = data.pop("id")
            sensor_data[sensor_id] = data

            with open("sensor_data_coap.json", "w") as f:
                json.dump(sensor_data, f, indent=2)
        except Exception:
            ...
        response = aiocoap.Message(code=aiocoap.CHANGED)
        return response


async def coap_server(host, port):
    root = aiocoap.resource.Site()
    root.add_resource([f"data"], CoAPResource())

    logger.info(f"Starting CoAP Backend Server ({host}:{port})")
    await aiocoap.Context.create_server_context(root, bind=(host, port))

    # Serve until process is killed
    await asyncio.get_running_loop().create_future()


def start_coap_server():
    asyncio.run(coap_server("0.0.0.0", 5684))


start_coap_server()
