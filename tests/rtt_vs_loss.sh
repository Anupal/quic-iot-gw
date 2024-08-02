TAG=$1
NUM_CLIENTS=$2
NUM_REQUESTS=$3
SAMPLES=$4
MAX_LOSS=$5
LOSS=0.0
PROTOCOL=$6

# usage: bash tests/rtt_vs_loss.sh <qig/tig> <num-clients> <num-requests> <samples> <max-loss> <protocol>

# Outer loop to increase packet loss by 0.5% each iteration, stopping at MAX_LOSS
while (( $(echo "$LOSS <= $MAX_LOSS" | bc -l) )); do
    # Format LOSS to ensure it has a leading zero if needed
    LOSS=$(printf "%.1f" $LOSS)
    echo -e "\n********************************** Loss: $LOSS **********************************"
    bash tests/core.sh $TAG $NUM_CLIENTS $NUM_REQUESTS $SAMPLES $LOSS $PROTOCOL
    # Increment the packet loss
    LOSS=$(echo "$LOSS + 0.5" | bc)
done