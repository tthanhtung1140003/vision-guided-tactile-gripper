# udp_receiver.py
import socket
import struct
import threading

class UDPForceReceiver:
    def __init__(self, port=5005):
        self.latest_force = (0.0, 0.0, 0.0)
        self.lock = threading.Lock()
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", port))

        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def _listen(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(1024)
                fx, fy, fz = struct.unpack("fff", data)

                with self.lock:
                    self.latest_force = (fx, fy, fz)

            except Exception:
                pass

    def get_latest(self):
        with self.lock:
            return self.latest_force

    def stop(self):
        self.running = False
        self.sock.close()
