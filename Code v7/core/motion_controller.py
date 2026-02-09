import time

class MotionController:
    def __init__(self, state, serial_mgr):
        self.state = state
        self.serial = serial_mgr
        self._last_send = 0.0
        self._pending_target = None

        if not hasattr(self.state, "target_pos"):
            self.state.target_pos = [self.state.pos[0], self.state.pos[1], self.state.pos[2]]
    # ================= BASIC COMMANDS =================
    def goto_throttled(self, x, y, z, force=False, min_interval=0.05):
        t = time.monotonic()
        self._pending_target = (x, y, z)

        if force or (t - self._last_send) >= min_interval:
            self._last_send = t
            tx, ty, tz = self._pending_target
            self._pending_target = None
            self.state.target_pos[0] = tx
            self.state.target_pos[1] = ty
            self.state.target_pos[2] = tz

            self.serial.send(f"MOVE X {tx:.3f} Y {ty:.3f} Z {tz:.3f}")

    def home(self):
        if hasattr(self.state, "target_pos"):
            self.state.target_pos[0] = 0.0
            self.state.target_pos[1] = 0.0
            self.state.target_pos[2] = 0.0
        self.serial.send("HOME")

    def resume(self):
        self.serial.send("ACK")
        self.state.target_pos[:] = self.state.pos[:]

    def stop(self):
        self.serial.send("STOP")
        self.state.target_pos[:] = self.state.pos[:]

    # ================= JOG =================
    def jog(self, axis: str, step: float):
        if axis not in ("X", "Y", "Z"):
            return

        idx = "XYZ".index(axis)
        self.state.target_pos[idx] = self.state.target_pos[idx] + step

        sign = "+" if step >= 0 else "-"
        self.serial.send(f"JOG {axis}{sign}{abs(step)}")

    # ================= ABS MOVE =================
    def move_abs(self, x, y, z):
        self.state.target_pos[0] = float(x)
        self.state.target_pos[1] = float(y)
        self.state.target_pos[2] = float(z)

        self.serial.send(f"MOVE X {x:.3f} Y {y:.3f} Z {z:.3f}")
