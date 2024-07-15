import logging
import asyncio
import mqtt_sn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    gw = mqtt_sn.gateway.Gateway(host='localhost', port=1883)
    try:
        await gw.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
        await gw.stop()


if __name__ == "__main__":
    asyncio.run(main())
