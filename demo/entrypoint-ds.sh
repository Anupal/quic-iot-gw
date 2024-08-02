#!/bin/bash

echo "entrypoint-ds"

touch logs

# Run the Python scripts
python coap_server.py &> logs &
python mqtt_sub.py &> logs &
python dashboard.py &> logs &

tail -f logs

echo "exiting..."

# Sleep indefinitely
sleep infinity