import socket, struct, sys, time
class RCON:
    def __init__(self, host='127.0.0.1', port=27115, pw='mtpass'):
        self.s = socket.create_connection((host, port), timeout=10)
        self.id = 0
        self._send(3, pw); self._recv_all(0.5)
    def _send(self, typ, body):
        self.id += 1
        b = body.encode() + b'\x00\x00'
        self.s.sendall(struct.pack('<iii', len(b) + 8, self.id, typ) + b)
        return self.id
    def _recv_all(self, wait):
        self.s.settimeout(wait); out = b''
        try:
            while True:
                d = self.s.recv(65536)
                if not d: break
                out += d
        except socket.timeout: pass
        res = []; i = 0
        while i + 12 <= len(out):
            ln, rid, typ = struct.unpack_from('<iii', out, i)
            res.append(out[i+12:i+4+ln-2].decode('latin1')); i += 4 + ln
        return ''.join(res)
    def cmd(self, c, wait=0.4):
        self._send(2, c); return self._recv_all(wait)
if __name__ == '__main__':
    r = RCON(); print(r.cmd(' '.join(sys.argv[1:]), 1.0))
