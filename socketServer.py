# -*- coding: utf-8 -*-
import socket

HOST = ''
PORT = 61617
BUFSIZE = 1024
ADDR = (HOST, PORT)

# 소켓 생성 (IPv6, UDP)
serverSocket = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

# 소켓 주소 정보 할당
serverSocket.bind(ADDR)
print('bind addr')

# 클라이언트로부터 메시지를 가져옴
data, addr = serverSocket.recvfrom(BUFSIZE)
print("receive data : ", data.decode())
print("receive addr :", addr)

# 소켓 종료
serverSocket.close()
print('close')