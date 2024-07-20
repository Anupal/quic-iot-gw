import struct
from enum import IntEnum


class MessageType(IntEnum):
    ADVERTISE = 0x00
    SEARCHGW = 0x01
    GWINFO = 0x02
    CONNECT = 0x04
    CONNACK = 0x05
    WILLTOPICREQ = 0x06
    WILLTOPIC = 0x07
    WILLMSGREQ = 0x08
    WILLMSG = 0x09
    REGISTER = 0x0A
    REGACK = 0x0B
    PUBLISH = 0x0C
    PUBACK = 0x0D
    PUBCOMP = 0x0E
    PUBREC = 0x0F
    PUBREL = 0x10
    SUBSCRIBE = 0x12
    SUBACK = 0x13
    UNSUBSCRIBE = 0x14
    UNSUBACK = 0x15
    PINGREQ = 0x16
    PINGRESP = 0x17
    DISCONNECT = 0x18
    WILLTOPICUPD = 0x1A
    WILLTOPICRESP = 0x1B
    WILLMSGUPD = 0x1C
    WILLMSGRESP = 0x1D


class TopicType(IntEnum):
    NORMAL = 0b00
    PREDEFINED = 0b01
    SHORT = 0b10


class ReturnCode(IntEnum):
    ACCEPTED = 0x00
    CONGESTION = 0x01
    INVALID_TOPIC = 0x02
    NOT_SUPPORTED = 0x03


class MQTTSNPacketDecoder:
    def decode(self, message):
        if len(message) < 2:
            raise ValueError("Message too short")

        length = message[0]
        message_type = message[1]
        message = message[2:]

        if message_type == MessageType.CONNECT:
            return self._decode_connect(message)
        elif message_type == MessageType.CONNACK:
            return self._decode_connack(message)
        elif message_type == MessageType.PUBLISH:
            return self._decode_publish(message)
        elif message_type == MessageType.PUBACK:
            return self._decode_puback(message)
        elif message_type == MessageType.REGISTER:
            return self._decode_register(message)
        elif message_type == MessageType.REGACK:
            return self._decode_regack(message)
        else:
            raise ValueError("Unknown/Unsupported message type")

    def _decode_connect(self, payload):
        if len(payload) < 6:
            raise ValueError("Invalid CONNECT message length")
        flags, protocol_id, duration = struct.unpack("!BBH", payload[:4])
        client_id = payload[4:].decode('utf-8')
        return {
            "type": MessageType.CONNECT,
            "flags": self._decode_flags(flags),
            "protocol_id": protocol_id,
            "duration": duration,
            "client_id": client_id
        }

    def _decode_connack(self, payload):
        if len(payload) != 1:
            raise ValueError("Invalid CONNACK message length")
        return {
            "type": MessageType.CONNACK,
            "return_code": payload[0]
        }

    def _decode_flags(self, flags):
        # flags = int.from_bytes(flags, "big")
        return  {
            "dup": bool(flags & 0b10000000),
            "qos": (flags & 0b01100000) >> 5,
            "retain": bool(flags & 0b00010000),
            "will": bool(flags & 0b00001000),
            "clean_session": bool(flags & 0b00000100),
            "topic_type": flags & 0b00000011,
        }

    def _decode_publish(self, payload):
        if len(payload) < 7:
            raise ValueError("Invalid PUBLISH message length")
        flags = payload[0]
        topic_id = struct.unpack("!H", payload[1:3])[0]
        msg_id = struct.unpack("!H", payload[3:5])[0]
        data = payload[5:].decode('utf-8')
        return {
            "type": MessageType.PUBLISH,
            "flags": self._decode_flags(flags),
            "topic_id": topic_id,
            "msg_id": msg_id,
            "data": data
        }

    def _decode_puback(self, payload):
        if len(payload) != 5:
            raise ValueError("Invalid PUBACK message length")
        topic_id, msg_id, return_code = struct.unpack("!HHB", payload)
        return {
            "type": MessageType.PUBACK,
            "topic_id": topic_id,
            "msg_id": msg_id,
            "return_code": return_code
        }

    def _decode_register(self, payload):
        if len(payload) < 6:
            raise ValueError("Invalid REGISTER message length")
        topic_id = struct.unpack("!H", payload[0:2])[0]
        msg_id = struct.unpack("!H", payload[2:4])[0]
        topic_name = payload[4:].decode('utf-8')
        return {
            "type": MessageType.REGISTER,
            "topic_id": topic_id,
            "msg_id": msg_id,
            "topic_name": topic_name
        }

    def _decode_regack(self, payload):
        if len(payload) != 5:
            raise ValueError("Invalid REGACK message length")
        topic_id, msg_id, return_code = struct.unpack("!HHB", payload)
        return {
            "type": MessageType.REGACK,
            "topic_id": topic_id,
            "msg_id": msg_id,
            "return_code": return_code
        }


class MQTTSNPacketEncoder:
    def encode(self, *args, **kwargs):
        message_type = kwargs.pop("type")
        if message_type == MessageType.CONNECT:
            return self._encode_connect(**kwargs)
        elif message_type == MessageType.CONNACK:
            return self._encode_connack(**kwargs)
        elif message_type == MessageType.PUBLISH:
            return self._encode_publish(**kwargs)
        elif message_type == MessageType.PUBACK:
            return self._encode_puback(**kwargs)
        elif message_type == MessageType.REGISTER:
            return self._encode_register(**kwargs)
        elif message_type == MessageType.REGACK:
            return self._encode_regack(**kwargs)
        else:
            return None

    def _encode_connect(self, flags, protocol_id, duration, client_id):
        encoded_flags = self._encode_flags(flags)
        client_id_bytes = client_id.encode('utf-8')
        payload = struct.pack(
            "!BBBH",  # Format: length byte, message type byte, flags byte, protocol ID byte, duration (2 bytes)
            MessageType.CONNECT,  # Message Type
            encoded_flags,  # Flags
            protocol_id,  # Protocol ID
            duration  # Duration
        )
        payload += client_id_bytes
        return struct.pack("!B", len(payload)) + payload

    def _encode_connack(self, return_code):
        length = 3
        message_type = MessageType.CONNACK
        payload = struct.pack("!BB", message_type, return_code)
        return struct.pack("!B", length) + payload

    def _encode_flags(self, values):
        flags = 0
        if values.get("dup", False):
            flags |= 0b10000000
        if values.get("qos", 0) in [1, 2]:
            flags |= (values["qos"] << 5)
        if values.get("retain", False):
            flags |= 0b00010000
        if values.get("will", False):
            flags |= 0b00001000
        if values.get("clean_session", False):
            flags |= 0b00000100
        if values.get("topic_type", 0) in [0, 1, 2, 3]:
            flags |= values["topic_type"]
        return flags

    def _encode_publish(self, flags, topic_id, msg_id, data):
        message_type = MessageType.PUBLISH
        encoded_flags = self._encode_flags(flags)
        payload = struct.pack("!BBHH", message_type, encoded_flags, topic_id, msg_id)
        payload += data.encode('utf-8')
        length = 1 + len(payload)  # Length byte + payload
        return struct.pack("!B", length) + payload

    def _encode_puback(self, topic_id, msg_id, return_code):
        length = 7
        message_type = MessageType.PUBACK
        payload = struct.pack("!BH", message_type, topic_id)
        payload += struct.pack("!HB", msg_id, return_code)
        return struct.pack("!B", length) + payload

    def _encode_register(self, topic_id, msg_id, topic_name):
        length = 6 + len(topic_name)
        message_type = MessageType.REGISTER
        payload = struct.pack("!BH", message_type, topic_id)
        payload += struct.pack("!H", msg_id)
        payload += topic_name.encode('utf-8')
        return struct.pack("!B", length) + payload

    def _encode_regack(self, topic_id, msg_id, return_code):
        length = 7
        message_type = MessageType.REGACK
        payload = struct.pack("!BH", message_type, topic_id)
        payload += struct.pack("!HB", msg_id, return_code)
        return struct.pack("!B", length) + payload

    def _encode_disconnect(self):
        length = 2
        message_type = MessageType.DISCONNECT
        payload = struct.pack("!B", message_type)
        return struct.pack("!B", length) + payload


class RegisteredTopics:
    def __init__(self):
        self.clients = {}
        self.clients_rev = {}
        self._topic_id_tracker = {}

    def add_topic(self, client_id, topic_name):
        if client_id not in self.clients:
            topic_id = self._next_topic_id(client_id)
            self.clients[client_id] = {topic_name: topic_id}
            self.clients_rev[client_id] = {topic_id: topic_name}
            return topic_id
        elif topic_name in self.clients[client_id]:
            return self.clients[client_id][topic_name]
        else:
            topic_id = self._next_topic_id(client_id)
            self.clients[client_id][topic_name] = topic_id
            self.clients_rev[client_id][topic_id] = topic_name
            return topic_id

    def topic_id_to_name(self, client_id, topic_id):
        return self.clients_rev.get(client_id, {}).get(topic_id, None)

    def topic_name_to_id(self, client_id, topic_name):
        return self.clients.get(client_id, {}).get(topic_name, None)

    def _next_topic_id(self, client_id):
        topic_id = self._topic_id_tracker.get(client_id, 1)
        self._topic_id_tracker[client_id] = topic_id + 1
        return topic_id


decoder = MQTTSNPacketDecoder()
encoder = MQTTSNPacketEncoder()


if __name__ == '__main__':
    decoder = MQTTSNPacketDecoder()
    msq = decoder.decode(b"\x0C\x12\x34\x56\x78\x48\x65\x6C\x6C\x6F\x21")
    print(msq)
