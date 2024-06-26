import aiocoap.resource as resource
import aiocoap
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoAPResource(resource.Resource):
    def __init__(self):
        super().__init__()
        self.content = b"Hello, CoAP from backend server!"

    async def render_get(self, request):
        logger.info(f"Received GET request: {request}")
        response = aiocoap.Message(payload=self.content)
        logger.info(f"Sending response: {self.content} | {response}")
        return response

    async def render_post(self, request):
        logger.info(f"Received POST request: {request}")
        self.content = request.payload
        return aiocoap.Message(code=aiocoap.CHANGED, payload=self.content)


async def main():
    root = resource.Site()
    root.add_resource(['hello'], CoAPResource())

    logger.info("Starting CoAP Backend Server")
    await aiocoap.Context.create_server_context(root, bind=("localhost", 5684))

    # Serve until process is killed
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
