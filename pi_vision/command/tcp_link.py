#command/tcp_link
import socket
import threading
import queue
import time

class TcpLink:
    def __init__(self, role="server", host="0.0.0.0", port=9999, name="LAPTOP_TCP"):
        self.role = role.lower()
        self.host = host
        self.port = port
        self.name = name
        self.sock = None
        self.conn = None
        self.addr = None
        self.running = True
        self.rx_queue = queue.Queue()

        print(f"[{name}] Khởi tạo role={role}, host={host}, port={port}")

        if role == "server":
            self._start_server()
        else:
            self._start_client()

        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _start_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.host, self.port))
            self.sock.listen(1)
            print(f"[{self.name}] Đang lắng nghe {self.host}:{self.port} ...")
            self.conn, self.addr = self.sock.accept()
            print(f"[{self.name}] Kết nối từ {self.addr}")
        except Exception as e:
            print(f"[{self.name}] Server lỗi: {e}")
            self.running = False

    def _start_client(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                print(f"[{self.name}] Đang kết nối {self.host}:{self.port} ...")
                self.sock.connect((self.host, self.port))
                self.conn = self.sock
                print(f"[{self.name}] Đã kết nối")
                break
            except Exception as e:
                print(f"[{self.name}] Không kết nối được, thử lại sau 3s... ({e})")
                time.sleep(3)

    def _receive_loop(self):
        while self.running:
            if not self.conn:
                time.sleep(0.3)
                continue
            try:
                data = self.conn.recv(1024).decode('utf-8', errors='ignore').strip()
                if not data:
                    print(f"[{self.name}] Phía kia đóng kết nối")
                    self.conn = None
                    if self.role == "client":
                        print(f"[{self.name}] Thử kết nối lại...")
                        self._start_client()
                    continue
                print(f"[RX {self.name}] {data}")
                self.rx_queue.put(data)
            except Exception as e:
                print(f"[{self.name}] Lỗi nhận: {e}")
                self.conn = None
                time.sleep(1)

    def send(self, msg: str):
        if not self.conn:
            print(f"[{self.name}] Không có kết nối → không gửi")
            return
        if not msg.endswith("\n"):
            msg += "\n"
        try:
            self.conn.send(msg.encode('utf-8'))
            print(f"[TX {self.name}] {msg.strip()}")
        except Exception as e:
            print(f"[{self.name}] Lỗi gửi: {e}")
            self.conn = None

    def read(self) -> str | None:
        if not self.rx_queue.empty():
            return self.rx_queue.get()
        return None

    def close(self):
        self.running = False
        if self.conn:
            try: self.conn.close()
            except: pass
        if self.sock:
            try: self.sock.close()
            except: pass
        print(f"[{self.name}] Đã đóng")