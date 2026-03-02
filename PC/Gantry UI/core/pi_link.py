import threading
import time
import socket
from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable, Deque, Tuple


@dataclass
class PiMessage:
    msg_type: str   # CMD / EVT / ACK
    seq: int
    mode: str       # GRASP / HOLD / HANDOVER / TRACK
    payload: str
    raw: str


class PiLink:
    """
    TCP link to Raspberry Pi.

    Line-based protocol (UTF-8), one packet per line.

    Compatibility notes:
      - New Pi-side protocol can be plain text commands/events, e.g. "Grasping_Mode" or "Move X+".
      - Older framed protocol (TYPE|SEQ|MODE|PAYLOAD) is still accepted on RX.

    Reliability:
      - send_cmd(...) will send a single line. ACK/SEQ is no longer required in the TCP text protocol,
        but we keep the method for backward compatibility.
      - received lines are queued for the GUI thread to consume via poll()/poll_lines().
    """
    def __init__(
        self,
        host: str,
        port: int = 9999,
        *,
        on_rx_line: Optional[Callable[[str], None]] = None,
        rx_maxlen: int = 2000,
    ):
        self.host = host
        self.port = port
        self.on_rx_line = on_rx_line

        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self._rxq: Deque[PiMessage] = deque(maxlen=rx_maxlen)
        self._rx_lines: Deque[str] = deque(maxlen=rx_maxlen)

        # Legacy fields kept for compatibility; not used in the raw TCP text protocol.
        self._seq = 100
        self._ack_lock = threading.Lock()
        self._ack_wait = {}

        self._tx_lock = threading.Lock()

    def is_open(self) -> bool:
        return self._sock is not None

    def open(self, timeout: float = 0.1) -> None:
        if self.is_open():
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((self.host, self.port))
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        finally:
            self._sock = None

    def _next_seq(self) -> int:
        self._seq += 1
        if self._seq > 999999:
            self._seq = 100
        return self._seq

    def _rx_loop(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                if not self._sock:
                    time.sleep(0.05)
                    continue
                chunk = self._sock.recv(256)
                if not chunk:
                    # Connection closed by peer
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        s = line.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        s = ""
                    if not s:
                        continue
                    if self.on_rx_line:
                        try:
                            self.on_rx_line(s)
                        except Exception:
                            pass
                    # Always keep raw line queue
                    self._rx_lines.append(s)

                    # Backward compatible parse for framed protocol
                    msg = self._parse_line(s)
                    if msg:
                        self._handle_msg(msg)
                    else:
                        # For raw protocol, expose as a synthetic EVT so older GUI handlers can still work.
                        self._rxq.append(PiMessage(msg_type="EVT", seq=0, mode="RAW", payload=s, raw=s))
            except Exception:
                # If connection fails, slow down and keep loop alive.
                time.sleep(0.1)

    def _parse_line(self, s: str) -> Optional[PiMessage]:
        parts = s.split("|")
        if len(parts) < 4:
            return None
        msg_type = parts[0].strip().upper()
        try:
            seq = int(parts[1].strip())
        except Exception:
            return None
        mode = parts[2].strip().upper()
        payload = "|".join(parts[3:]).strip()
        return PiMessage(msg_type=msg_type, seq=seq, mode=mode, payload=payload, raw=s)

    def _handle_msg(self, msg: PiMessage) -> None:
        if msg.msg_type == "ACK":
            with self._ack_lock:
                entry = self._ack_wait.get(msg.seq)
                if entry:
                    ev, _ = entry
                    self._ack_wait[msg.seq] = (ev, msg.payload)
                    ev.set()
            return
        # Queue EVT or CMD (if Pi ever sends CMD)
        self._rxq.append(msg)

    def poll(self, max_items: int = 50) -> list[PiMessage]:
        out = []
        for _ in range(max_items):
            if not self._rxq:
                break
            out.append(self._rxq.popleft())
        return out

    def poll_lines(self, max_items: int = 50) -> list[str]:
        out: list[str] = []
        for _ in range(max_items):
            if not self._rx_lines:
                break
            out.append(self._rx_lines.popleft())
        return out

    def send_raw(self, line: str) -> None:
        if not self.is_open():
            raise RuntimeError("PiLink not connected")
        if not line.endswith("\n"):
            line += "\n"
        data = line.encode("utf-8")
        with self._tx_lock:
            self._sock.sendall(data)

    def send_cmd(
        self,
        mode: str,
        payload: str = "",
        *,
        require_ack: bool = False,
        retries: int = 1,
        ack_timeout: float = 0.25,
    ) -> Tuple[bool, Optional[str], int]:
        """Send a single command line to Pi.

        In the raw TCP text protocol, the command is simply a line like:
          - "Grasping_Mode"
          - "Approach_Done"
          - "Tracking_Mode_Done"

        We keep the old signature for compatibility. The sent line will be:
          - payload (if provided) else mode

        Returns: (ok, ack_payload, seq). ack_payload/seq are legacy and unused.
        """
        cmd = (payload or mode or "").strip()
        if not cmd:
            return False, None, 0
        try:
            self.send_raw(cmd)
            return True, None, 0
        except Exception:
            return False, None, 0

    def send_ack(self, seq: int, mode: str, payload: str = "OK") -> None:
        # Raw TCP text protocol does not require ACK; keep as no-op for compatibility.
        return
