TAG=$1
NUM_REQUESTS=$2
SAMPLES=$3
LOSS=$4
PROTOCOL=$5

# usage: bash tests/rtt_vs_num_clients.sh <qig/tig> <num-requests> <samples> <loss> <protocol>

# Array of client counts
NUM_CLIENT_COUNTS=(100 150 200 250 300)

for NUM_CLIENTS in "${NUM_CLIENT_COUNTS[@]}"; do
    echo -e "\n********************************** Number of clients: $NUM_CLIENTS **********************************"
    bash tests/core.sh $TAG $NUM_CLIENTS $NUM_REQUESTS $SAMPLES $LOSS $PROTOCOL
done