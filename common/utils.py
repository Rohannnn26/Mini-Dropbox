import json, struct

def send_msg(sock, msg):
    """Send JSON message with length prefix."""
    data = json.dumps(msg).encode()
    sock.sendall(struct.pack("!I", len(data)))
    sock.sendall(data)

def recv_msg(sock):
    """Receive JSON message with length prefix."""
    raw_len = recvall(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack("!I", raw_len)[0]
    data = recvall(sock, msg_len)
    return json.loads(data.decode())

def recvall(sock, n):
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data
