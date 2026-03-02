# command/laptop_link.py
from command.tcp_link import TcpLink

class LaptopLink:
    def __init__(self, role="server", host="0.0.0.0", port=9999):
        self.link = TcpLink(role=role, host=host, port=port, name="LAPTOP_TCP")

    def send(self, msg):
        self.link.send(msg)

    def read(self):
        return self.link.read()

    def close(self):
        self.link.close()