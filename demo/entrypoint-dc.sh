#!/bin/bash

echo "entrypoint-dc"

touch logs

# Run the Python scripts
python coap_client.py &> logs &
python mqtt_sn_client.py %> logs &

tail -f logs

echo "exiting..."

# Sleep indefinitely
sleep infinity