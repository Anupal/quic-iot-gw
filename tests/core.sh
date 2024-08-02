#!/bin/bash

TAG=$1
CLIENT_CONTAINER=$1-client
#SERVER_CONTAINER=$1-server
NUM_CLIENTS=$2
NUM_REQUESTS=$3
SAMPLES=$4
LOSS=$5
PROTOCOL=$6

# Function to get the veth interface for a given container
get_veth_interface() {
    local container=$1
    local iflink

    # Get the iflink value for eth0 in the container
    iflink=$(docker exec -it $container bash -c 'cat /sys/class/net/eth0/iflink')
    iflink=$(echo $iflink | tr -d '\r')

    # Find the veth interface corresponding to the iflink
    veth=$(grep -l $iflink /sys/class/net/veth*/ifindex)
    veth=$(echo $veth | sed -e 's;^.*net/\(.*\)/ifindex$;\1;')

    echo $veth
}

# Function to clean up network settings
cleanup_network() {
    local veth=$1
    sudo tc qdisc del dev $veth root 2>/dev/null
}

# Function to analyze tcpdump capture
analyze_tcpdump() {
    local pcap_file=$1
    capinfos -M $pcap_file
}


# Inner loop to execute commands SAMPLES times
for ((j=0; j<$SAMPLES; j++)); do
  echo -e "\n>>>>>>>>>>>>>>>>[Iteration $((j + 1))]<<<<<<<<<<<<<<<<<<<<"

  docker rm -f scale-$PROTOCOL-clients
  make stop-$TAG
  make start-$TAG
  sleep 10

  # Get veth interface for the client container
  CLIENT_VETH=$(get_veth_interface $CLIENT_CONTAINER)

  # Apply network emulation settings
  cleanup_network $CLIENT_VETH
  sudo tc qdisc add dev $CLIENT_VETH root netem loss ${LOSS}%
  echo "> Applied netem with loss ${LOSS}% to $CLIENT_VETH"

  # Check if the client container is already running and remove it if it is
  if [ "$(docker ps -aq -f name=scale-$PROTOCOL-clients)" ]; then
      docker rm -f scale-$PROTOCOL-clients
  fi
  echo "> Run client container"

  if [ "$PROTOCOL" == "coap" ]; then
    echo "Running Docker container for scale coap clients..."
    docker run -d \
      --name scale-coap-clients \
      --network iot \
      qig \
      bash -c "coap_client \
        --message_size_range 490,510 \
        --coap-server-host coap-server \
        --coap-server-port 5684 \
        --coap-proxy-host $CLIENT_CONTAINER \
        --coap-proxy-port 5683 \
        --num-clients $NUM_CLIENTS \
        --num-requests $NUM_REQUESTS \
        --starting-port 30001 \
        --req-type post \
        --loops 1 \
        --log-level CRITICAL"
  elif [ "$PROTOCOL" == "mqtt-sn" ]; then
    echo "Running Docker container for scale mqtt-sn clients..."
    docker run -d \
      --name scale-mqtt-sn-clients \
      --network iot \
      qig \
      bash -c "mqtt_sn_client \
        --message_size_range 490,510 \
        --mqtt-sn-gw-host $CLIENT_CONTAINER \
        --mqtt-sn-gw-port 1883 \
        --num-clients $NUM_CLIENTS \
        --num-requests $NUM_REQUESTS \
        --num-topics 10 \
        --starting-port 31001 \
        --loops 1 \
        --log-level CRITICAL"
  else
    echo "Invalid PROTOCOL value. Must be either 'coap' or 'mqtt-sn'."
    exit 1
  fi

  # Run the client container


  # Start tcpdump in the background to capture traffic on the client container
  echo "> Start tcpdump on $CLIENT_CONTAINER"
  docker exec -d $CLIENT_CONTAINER tcpdump -i eth0 -w /tmp/tcpdump_capture.pcap

  echo "> Capture client container logs"
  docker logs -f scale-$PROTOCOL-clients

  # Stop tcpdump
  echo "> Stop tcpdump on $CLIENT_CONTAINER"
  docker exec $CLIENT_CONTAINER pkill -SIGINT tcpdump

  # Copy the pcap file to the host
  docker cp $CLIENT_CONTAINER:/tmp/tcpdump_capture.pcap ./tcpdump_capture_${LOSS}_${j}.pcap
  docker exec $CLIENT_CONTAINER rm /tmp/tcpdump_capture.pcap


  # Print the number of packets and bytes captured
  echo "> Analyzing tcpdump capture"
  analyze_tcpdump ./tcpdump_capture_${LOSS}_${j}.pcap

  # Stop and remove the client container
  echo "> Remove client container"
  docker rm -f scale-$PROTOCOL-clients
  make stop-$TAG

  rm ./tcpdump_capture_${LOSS}_${j}.pcap
done

echo "Completed iterations for loss ${LOSS}%"
