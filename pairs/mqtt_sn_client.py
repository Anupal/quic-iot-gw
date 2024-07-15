import socket

HOST, PORT = "localhost", 1883

msg_connect = b"\x0E\x04\x00\x01\x00\x0Aclient1" # CONNECT
msg_register = b"\x0D\x0A\x00\x00\x00\x01teso" # REGISTER
msg_publish = b"\x10\x0C\x00\x00\x01\x00\x01Hello" # PUBLISH

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("localhost", 33000))
s.sendto(msg_connect, (HOST, PORT))
s.sendto(msg_register, (HOST, PORT))
s.sendto(msg_publish, (HOST, PORT))