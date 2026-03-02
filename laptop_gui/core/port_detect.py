from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Dict, Any

import serial
from serial.tools import list_ports


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str = ""
    hwid: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None

    @property
    def vidpid(self) -> Optional[str]:
        if self.vid is None or self.pid is None:
            return None
        return f"{self.vid:04x}:{self.pid:04x}"


def list_all_ports() -> List[PortInfo]:
    """Return all available serial ports with metadata."""
    out: List[PortInfo] = []
    for p in list_ports.comports():
        out.append(
            PortInfo(
                device=p.device,
                description=getattr(p, "description", "") or "",
                hwid=getattr(p, "hwid", "") or "",
                vid=getattr(p, "vid", None),
                pid=getattr(p, "pid", None),
                serial_number=getattr(p, "serial_number", None),
                manufacturer=getattr(p, "manufacturer", None),
                product=getattr(p, "product", None),
            )
        )
    return out


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def match_signature(
    p: PortInfo,
    *,
    vid: Optional[int] = None,
    pid: Optional[int] = None,
    serial_number: Optional[str] = None,
    desc_contains: Optional[Sequence[str]] = None,
) -> bool:

    if vid is not None and p.vid != vid:
        return False
    if pid is not None and p.pid != pid:
        return False
    if serial_number and (p.serial_number != serial_number):
        return False

    if desc_contains:
        hay = " ".join([_norm(p.description), _norm(p.manufacturer), _norm(p.product)])
        needles = [_norm(x) for x in desc_contains if x]
        if not any(n and n in hay for n in needles):
            return False

    return True


def try_handshake_stm32(
    port: str,
    *,
    baud: int = 115200,
    timeout_s: float = 0.2,
    probe: bytes = b"?\n",
    expect_substr: str = "STATE=",
    max_wait_s: float = 0.6,
) -> bool:
    """Verify STM32 gantry controller by sending '?' and expecting 'STATE=' in response."""
    try:
        with serial.Serial(port, baudrate=baud, timeout=timeout_s) as ser:
            # Flush any stale bytes
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            ser.write(probe)
            ser.flush()

            t0 = time.time()
            while time.time() - t0 < max_wait_s:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if expect_substr in line:
                    return True
    except Exception:
        return False
    return False


def try_handshake_pi(
    port: str,
    *,
    baud: int = 115200,
    timeout_s: float = 0.2,
    seq: int = 1,
    max_wait_s: float = 0.6,
) -> bool:
    """Verify PiLink by sending a PING and expecting a PONG/ACK."""
    ping = f"CMD|{seq}|SYS|PING\n".encode("utf-8")
    try:
        with serial.Serial(port, baudrate=baud, timeout=timeout_s) as ser:
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            ser.write(ping)
            ser.flush()

            t0 = time.time()
            while time.time() - t0 < max_wait_s:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                # Accept either explicit PONG or any ACK for this seq in SYS mode.
                if "PONG" in line:
                    return True
                if line.startswith(f"ACK|{seq}|SYS|"):
                    return True
    except Exception:
        return False
    return False


def auto_detect_ports(
    *,
    stm32_sig: Optional[Dict[str, Any]] = None,
    pi_sig: Optional[Dict[str, Any]] = None,
    stm32_baud: int = 115200,
    pi_baud: int = 115200,
    use_handshake: bool = True,
    exclude_devices: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], Optional[str], List[PortInfo]]:
    """Attempt to find STM32 and Pi ports automatically.

    Returns: (stm32_port, pi_port, all_ports)
    """
    ports = list_all_ports()
    exclude = set(exclude_devices or [])

    stm32_sig = stm32_sig or {}
    pi_sig = pi_sig or {}

    # Signature candidates
    stm_cands = [p for p in ports if p.device not in exclude and match_signature(p, **stm32_sig)]
    pi_cands = [p for p in ports if p.device not in exclude and match_signature(p, **pi_sig)]

    # Fallback candidates (all)
    stm_scan = stm_cands or [p for p in ports if p.device not in exclude]
    pi_scan = pi_cands or [p for p in ports if p.device not in exclude]

    stm32_port: Optional[str] = None
    pi_port: Optional[str] = None

    if use_handshake:
        for p in stm_scan:
            if try_handshake_stm32(p.device, baud=stm32_baud):
                stm32_port = p.device
                break
    else:
        stm32_port = stm_scan[0].device if stm_scan else None

    # Exclude STM32 port when searching Pi
    exclude_pi = set(exclude)
    if stm32_port:
        exclude_pi.add(stm32_port)

    if use_handshake:
        for p in pi_scan:
            if p.device in exclude_pi:
                continue
            if try_handshake_pi(p.device, baud=pi_baud):
                pi_port = p.device
                break
    else:
        for p in pi_scan:
            if p.device in exclude_pi:
                continue
            pi_port = p.device
            break

    return stm32_port, pi_port, ports
