import serial
import threading
import time
import re


class SerialManager:
    STATUS_RE = re.compile(
        r"STATE\s*=\s*(\d+)\s+ERR\s*=\s*(\d+)\s+POS\s*=\s*"
        r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)"
        r"(?:\s+SPD\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?))?",
        re.IGNORECASE
    )

    def __init__(self, state, log_cb=None):
        self.state = state
        self.log_cb = log_cb

        self.ser = None
        self.thread = None

        self._running = False
        self._tx_lock = threading.Lock()
        self._disc_lock = threading.Lock()
        self._synced_target_once = False

    # ================= CONNECT =================
    def connect(self, port: str, baud: int):
        if self.ser and getattr(self.ser, "is_open", False):
            return False, "Already connected"

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=int(baud),
                timeout=0.1,
                write_timeout=0.2
            )
        except Exception as e:
            self.ser = None
            self.state.connected = False
            return False, str(e)

        self.state.connected = True
        self._running = True
        self._synced_target_once = False

        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()
        self.send("ACK")

        if self.log_cb:
            self.log_cb(f"Connected {port} @ {baud}", "INFO")

        return True, f"Connected {port} @ {baud}"

    # ================= DISCONNECT =================
    def disconnect(self, reason="DISCONNECT", join_timeout=0.5):
        """
        Idempotent disconnect. Safe to call from any thread.
        """
        with self._disc_lock:
            if not self.state.connected and (self.ser is None):
                return

            self._running = False
            self.state.connected = False
            try:
                if self.ser and getattr(self.ser, "is_open", False):
                    self.ser.close()
            except Exception:
                pass
            finally:
                self.ser = None
        t = self.thread
        if t and t.is_alive() and (threading.current_thread() is not t):
            t.join(timeout=join_timeout)

        if self.log_cb:
            self.log_cb(f"Disconnected: {reason}", "WARN")

    # ================= SEND =================
    def send(self, cmd: str):
        if not cmd:
            return
        if not self.ser or not getattr(self.ser, "is_open", False):
            return

        data = (cmd.strip() + "\n").encode("utf-8", errors="ignore")
        with self._tx_lock:
            try:
                self.ser.write(data)
            except Exception:
                self.disconnect(reason="WRITE_FAIL")

    # ================= READER THREAD =================
    def _reader_loop(self):
        buf = bytearray()
        try:
            while self._running and self.ser and getattr(self.ser, "is_open", False):
                try:
                    n = self.ser.in_waiting or 1
                    chunk = self.ser.read(n)
                except Exception:
                    break

                if chunk:
                    buf.extend(chunk)
                    while b"\n" in buf:
                        line_bytes, _, rest = bytes(buf).partition(b"\n")
                        buf = bytearray(rest)

                        line = line_bytes.decode("utf-8", errors="ignore").strip()
                        if line:
                            self._handle_line(line)

                time.sleep(0.005)

        finally:
            self.disconnect(reason="READ_LOOP_END")

    # ================= PARSE =================
    def _handle_line(self, line: str):
        if not line:
            return

        if line.startswith("["):
            self._handle_bracket_log(line)
            return

        up = line.upper()
        if up.startswith("ERR"):
            if self.log_cb:
                self.log_cb(line, "ERROR")
            return

        if self.log_cb:
            self.log_cb(line, "FW")

    def _handle_bracket_log(self, line: str):
        if line.startswith("[INFO]"):
            msg = line[6:].strip()


            if self._try_parse_status_from_info(msg):
                return

            if self.log_cb:
                self.log_cb(msg, "INFO")
            return

        if self.log_cb:
            if line.startswith("[WARN]"):
                self.log_cb(line[6:].strip(), "WARN")
            elif line.startswith("[ERROR]"):
                self.log_cb(line[7:].strip(), "ERROR")
            else:
                self.log_cb(line, "FW")

    def _try_parse_status_from_info(self, msg: str) -> bool:
        m = self.STATUS_RE.search(msg)
        if not m:
            return False

        try:
            fw_state = int(m.group(1))
            fw_err = int(m.group(2))
            x = float(m.group(3))
            y = float(m.group(4))
            z = float(m.group(5))

            # SPD có thể không có (firmware cũ) => default 0
            sx = float(m.group(6)) if m.group(6) is not None else 0.0
            sy = float(m.group(7)) if m.group(7) is not None else 0.0
            sz = float(m.group(8)) if m.group(8) is not None else 0.0
        except Exception:
            return False

        # feedback
        # apply soft-limits (0..max) to feedback to keep UI stable even if firmware overshoots
        try:
            lim = getattr(self.state, "limits", None)
            if isinstance(lim, dict):
                def _cl(a, v):
                    vmax = lim.get(a, None)
                    if vmax is None:
                        return v
                    try:
                        vmax = float(vmax)
                    except Exception:
                        return v
                    if v < 0.0:
                        return 0.0
                    if v > vmax:
                        return vmax
                    return v
                x = _cl("X", x)
                y = _cl("Y", y)
                z = _cl("Z", z)
        except Exception:
            pass

        self.state.pos[0] = x
        self.state.pos[1] = y
        self.state.pos[2] = z
        # mark fresh POS
        if hasattr(self.state, 'last_pos_ts'):
            try:
                import time as _time
                self.state.last_pos_ts = _time.monotonic()
            except Exception:
                pass

        if hasattr(self.state, "speed"):
            self.state.speed[0] = sx
            self.state.speed[1] = sy
            self.state.speed[2] = sz

        if hasattr(self.state, "fw_state"):
            self.state.fw_state = fw_state
        if hasattr(self.state, "fw_err"):
            self.state.fw_err = fw_err

        if (not self._synced_target_once) and hasattr(self.state, "target_pos"):
            self.state.target_pos[0] = x
            self.state.target_pos[1] = y
            self.state.target_pos[2] = z
            self._synced_target_once = True

        return True
