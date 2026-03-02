import threading
import time
import math


class PathEngine:
    def __init__(self, state, motion):
        self.state = state
        self.motion = motion
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

        self.on_active_point_changed = None
        self.arrive_eps = 0.20     # mm
        self.point_timeout = 60.0  # s
        self.poll_dt = 0.05        # s

    def is_running(self):
        with self._lock:
            return self._running
    # ================= PUBLIC API =================
    def start(self, start_index=0):
        with self._lock:
            if self._running:
                return
            if not self.state.points:
                return
            try:
                start_index = int(start_index)
            except Exception:
                start_index = 0

            n = len(self.state.points)
            if start_index < 0 or start_index >= n:
                start_index = 0

            self._running = True

        self._thread = threading.Thread(target=self._run, args=(start_index,), daemon=True)
        self._thread.start()

    def stop(self, join_timeout=1.0):
        with self._lock:
            self._running = False

        # join thread to ensure it's actually stopped
        t = self._thread
        if t and t.is_alive() and (threading.current_thread() is not t):
            t.join(timeout=join_timeout)

        # ensure highlight reset
        self.state.active_point_index = -1
        if self.on_active_point_changed:
            self.on_active_point_changed(-1)

    # ================= INTERNAL =================
    def _dist(self, a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        dz = a[2] - b[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _wait_arrive(self, target_xyz):
        t0 = time.monotonic()
        while self.is_running():
            # mất kết nối -> abort
            if not getattr(self.state, "connected", False):
                return False, "DISCONNECTED"

            # firmware báo lỗi -> abort (nếu bạn đã parse fw_err)
            if hasattr(self.state, "fw_err") and self.state.fw_err not in (None, 0):
                return False, f"FW_ERR={self.state.fw_err}"

            # tới điểm?
            if self._dist(self.state.pos, target_xyz) <= self.arrive_eps:
                return True, "ARRIVED"

            # timeout?
            if (time.monotonic() - t0) >= self.point_timeout:
                return False, "TIMEOUT"

            time.sleep(self.poll_dt)

        return False, "STOPPED"

    def _run(self, start_index=0):
        try:
            points = list(self.state.points)

            for i in range(start_index, len(points)):
                if not self.is_running():
                    break

                pt = points[i]

            # highlight point
                self.state.active_point_index = i
                if self.on_active_point_changed:
                    self.on_active_point_changed(i)

                tx = float(pt["x"])
                ty = float(pt["y"])
                tz = float(pt["z"])
                target = [tx, ty, tz]

                self.motion.goto_throttled(tx, ty, tz, force=True)

                ok, _reason = self._wait_arrive(target)
                if not ok:
                    break

        finally:
            with self._lock:
                self._running = False
            self.state.active_point_index = -1
            if self.on_active_point_changed:
                self.on_active_point_changed(-1)

