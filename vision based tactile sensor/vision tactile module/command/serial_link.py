# command/serial_link.py
import serial, threading, time

class SerialLink:
    def __init__(self, port, baud=115200, name="LINK"):
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.name = name
        time.sleep(2)

        self.rx = []
        self.running = True

        threading.Thread(target=self._rx_loop, daemon=True).start()
        print(f"✅ {name} connected: {port}")

    def send(self, msg):
        if not msg.endswith("\n"):
            msg += "\n"
        self.ser.write(msg.encode())
        print(f"[TX {self.name}] {msg.strip()}")

    def send_frame(self, cmd):
        frame = f"<{cmd}>"
        self.ser.write(frame.encode())
        print(f"[TX {self.name}] {frame}")

    def _rx_loop(self):
        while self.running:
            try:
                line = self.ser.readline().decode().strip()
                if line:
                    self.rx.append(line)
                    #print(f"[RX {self.name}] {line}")
            except:
                pass

    def read(self):
        if self.rx:
            return self.rx.pop(0)
        return None