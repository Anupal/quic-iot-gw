# quic-iot-gw
Multi-protocol aggregation over QUIC for IoT communication

## QUIC server certificate and private key
Can be generated using:
```bash
openssl req -new -newkey rsa:2048 -days 365 -nodes -x509 -keyout key.pem -out cert.pem
```

## CoAP Forward Proxy
- Used to push north-bound data from CoAP clients
- Deployed using two scripts - client-proxy.py and server-proxy.py
- A QUIC connection is maintained between the proxy-pair and data is multiplexed over multiple streams.
- The traffic flow is shown below:
```
coap-server --- server-proxy ==QUIC== client-proxy --- coap-client
                      <--- 
```
- The design is strictly north-bound.

## MQTT-SN proxy
This is currently under work.

### Topology

coap-server        qig-server        qig-client        coap-client 
MQTT broker                                            mqtt-sn-client

### Docker

```bash
docker compose -f docker-compose.simulation.yaml up -d
docker compose -f docker-compose.simulation.yaml down
```

```bash
docker build -t qig -f extras/qig.Dockerfile .
```