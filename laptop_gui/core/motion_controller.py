import time

class MotionController:
    def __init__(self, state, serial_mgr):
        self.state = state
        self.serial = serial_mgr
        self._last_send = 0.0
        self._pending_target = None

        # JOG burst protection
        self._jog_last_send = 0.0
        self._jog_pending = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self._jog_min_interval = 0.03  # ~33Hz max

        if not hasattr(self.state, "target_pos"):
            self.state.target_pos = [float(self.state.pos[0]), float(self.state.pos[1]), float(self.state.pos[2])]

        # Auto-ACK when firmware is STOPPED/ERROR (prevents dead motion after STOP/limit)
        self._last_ack_ts = 0.0

    def _auto_ack_if_needed(self):
        """If firmware is STOPPED/ERROR state, send ACK once to re-enable motion."""
        SYS_STOPPED = 5
        SYS_ERROR = 6
        fw_state = getattr(self.state, 'fw_state', None)
        if fw_state not in (SYS_STOPPED, SYS_ERROR):
            return
        now = time.monotonic()
        if (now - float(self._last_ack_ts or 0.0)) < 0.25:
            return
        self._last_ack_ts = now
        try:
            self.serial.send('ACK')
        except Exception:
            pass

    # ================= BASIC COMMANDS =================
    def goto_throttled(self, x, y, z, force=False, min_interval=0.05):
        """Send absolute MOVE with rate limit to avoid flooding firmware."""
        t = time.monotonic()
        self._pending_target = (float(x), float(y), float(z))

        if not (force or (t - self._last_send) >= float(min_interval)):
            return

        self._last_send = t
        tx, ty, tz = self._pending_target
        self._pending_target = None

        self._auto_ack_if_needed()

        # Clear any accumulated JOG burst
        self._jog_last_send = 0.0
        self._jog_pending = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}

        self.state.target_pos[0] = float(tx)
        self.state.target_pos[1] = float(ty)
        self.state.target_pos[2] = float(tz)

        self.serial.send(f"MOVE X {tx:.3f} Y {ty:.3f} Z {tz:.3f}")

    def home(self):
        if hasattr(self.state, "target_pos"):
            self.state.target_pos[:] = [0.0, 0.0, 0.0]
        self._auto_ack_if_needed()
        self.serial.send("HOME")

    def resume(self):
        self.serial.send("ACK")
        if hasattr(self.state, "target_pos"):
            self.state.target_pos[:] = self.state.pos[:]

    
    # ================= TRACKING (TVEL/TSTOP) =================
    def track_set_vel(self, vx=0.0, vy=0.0, vz=0.0):
        """Set tracking velocity in mm/s using TVEL (firmware velocity mode)."""
        self._auto_ack_if_needed()
        try:
            self.serial.send(f"TVEL X {float(vx):.3f} Y {float(vy):.3f} Z {float(vz):.3f}")
        except Exception:
            pass

    def track_stop(self):
        """Soft stop tracking mode without entering SYS_STOPPED (uses TSTOP)."""
        self._auto_ack_if_needed()
        try:
            self.serial.send("TSTOP")
        except Exception:
            pass

    def stop(self):
        self.serial.send("STOP")
        if hasattr(self.state, "target_pos"):
            self.state.target_pos[:] = self.state.pos[:]

    # ================= JOG =================
    def _clamp_axis(self, axis: str, v: float) -> float:
        lim = getattr(self.state, "limits", None)
        if lim and axis in lim:
            try:
                vmax = float(lim[axis])
                if v < 0.0:
                    return 0.0
                if v > vmax:
                    return vmax
            except Exception:
                pass
        return v

    def jog(self, axis: str, step: float, force: bool=False):
        """JOG theo POS/target + clamp + gộp burst để tránh rơi lệnh.

        - Base mặc định: state.pos
        - Nếu POS không được cập nhật gần đây (last_pos_ts stale), dùng state.target_pos làm base.
        - Nếu state.estimate_pos=True, mirror target vào pos để UI cập nhật realtime trong tracking.
        """
        axis = (axis or "").upper()
        if axis not in ("X", "Y", "Z"):
            return
        try:
            step = float(step)
        except Exception:
            return
        if abs(step) < 1e-9:
            return

        now = time.monotonic()
        self._jog_pending[axis] += step

        if (not force) and ((now - self._jog_last_send) < self._jog_min_interval):
            return

        total = self._jog_pending[axis]
        self._jog_pending[axis] = 0.0
        self._jog_last_send = now

        idx = "XYZ".index(axis)

        # Choose integration base
        base = float(self.state.pos[idx])
        try:
            ts = float(getattr(self.state, 'last_pos_ts', 0.0) or 0.0)
            if ts > 0.0 and (now - ts) > 0.25:
                base = float(self.state.target_pos[idx])
        except Exception:
            pass

        desired = self._clamp_axis(axis, base + total)
        delta = desired - base
        if abs(delta) < 1e-6:
            return

        self.state.target_pos[idx] = desired

        # During tracking, optionally estimate current pos for UI smoothness.
        if getattr(self.state, "estimate_pos", False):
            try:
                self.state.pos[idx] = desired
            except Exception:
                pass

        self._auto_ack_if_needed()

        sign = "+" if delta >= 0 else "-"
        self.serial.send(f"JOG {axis}{sign}{abs(delta):.3f}")

    def move_abs(self, x, y, z):
        x = float(x); y = float(y); z = float(z)
        self.state.target_pos[:] = [x, y, z]
        self._auto_ack_if_needed()
        self.serial.send(f"MOVE X {x:.3f} Y {y:.3f} Z {z:.3f}")
