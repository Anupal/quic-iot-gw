echo -e "\n\n############################## COAP ##########################################"
bash tests/rtt_vs_num_clients.sh qig 100 5 0.01 coap
echo -e "\n\n##############################################################################"
bash tests/rtt_vs_num_clients.sh tig 100 5 0.01 coap
echo -e "\n\n############################## MQTT ##########################################"
bash tests/rtt_vs_num_clients.sh qig 100 5 0.01 mqtt-sn
echo -e "\n\n##############################################################################"
bash tests/rtt_vs_num_clients.sh tig 100 5 0.01 mqtt-sn