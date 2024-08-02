
# coap_client.py
import logging
import time
import asyncio
import json

from aiocoap import Context, Message, POST
import random
import threading

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


PROXY_URI = "coap://qig-client:5683/proxy"
BACKEND_URI = "coap://demo-server:5684/data"


async def coap_client(index):
    context = await Context.create_client_context()

    protocol = "CoAP"
    sensor_type = random.choice(['Temperature', 'Humidity', 'Pressure'])
    lat = 53.3 + random.uniform(0.04, 0.05)
    lon = -6.3 + random.uniform(0.04, 0.05)

    while True:
        if sensor_type == 'Temperature':
            reading = f"{random.uniform(20, 25):.1f}°C"
        elif sensor_type == 'Humidity':
            reading = f"{random.randint(30, 60)}%"
        elif sensor_type == 'Pressure':
            reading = f"{random.randint(1000, 1020)} hPa"

        health = random.choice(['Good', 'Fair', 'Poor'])
        payload = json.dumps({
            'id': index,
            'type': sensor_type,
            'protocol': protocol,
            'reading': reading,
            'health': health,
            'lat': lat,
            'lon': lon
        })
        try:
            request = Message(uri=PROXY_URI, code=POST, payload=payload.encode())
            # logger.info(f"Sending: {request}")
            request.opt.proxy_uri = BACKEND_URI
            await context.request(request).response
        except Exception:
            logger.info("Error while sending request")
        await asyncio.sleep(5)


def td_coap_client(index):
    asyncio.run(coap_client(index))


if __name__ == "__main__":
    time.sleep(5)
    tds = []
    for index in range(1, 6):
        td = threading.Thread(target=td_coap_client, args=(index, ))
        tds.append(td)
        td.start()

    for td in tds:
        td.join()