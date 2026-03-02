# command/gripper.py
from command.serial_link import SerialLink
from command.protocol import *
import re

class Gripper:
    def __init__(self, port):
        self.link = SerialLink(port, name="GRIPPER")
        self.last_tar = None
        self.last_ang = None
    
    def update(self):
        msg = self.link.read()
        if msg:
            self._parse_feedback(msg)

    def _parse_feedback(self, msg: str):
        """
        Expect: <ANG:538.33,TAR:542.00>
        """

        ang_match = re.search(r"ANG:([0-9.]+)", msg)
        tar_match = re.search(r"TAR:([0-9.]+)", msg)

        if ang_match:
            self.last_ang = float(ang_match.group(1))

        if tar_match:
            self.last_tar = float(tar_match.group(1))

    def grasp(self,deg):
        self.link.send_frame(f"{GRIP_CLOSE}:{deg}")

    def stop(self):
        self.link.send_frame(GRIP_STOP)

    def squeeze(self, deg):
        self.link.send_frame(f"{GRIP_SQUEEZE}:{deg}")

    def loosen(self, deg):
        self.link.send_frame(f"{GRIP_LOOSEN}:{deg}")

    def open(self):
        self.link.send_frame(GRIP_OPEN)

    def read_state(self):
        return self.link.read()