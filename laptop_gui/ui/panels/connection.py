import os
import serial.tools.list_ports
from ui.widgets.figma import create_button_group, create_entry_group, create_combobox_group


class ConnectionPanel:
    def __init__(self, parent, serial_mgr, log_cb, *, pi_connect_fn=None, pi_disconnect_fn=None):
        self.parent = parent
        self.serial_mgr = serial_mgr
        self.log = log_cb  

        # Pi connect/disconnect callbacks (owned by AppUI)
        self.pi_connect_fn = pi_connect_fn
        self.pi_disconnect_fn = pi_disconnect_fn

        # Optional signatures to auto-detect ports (VID/PID/SN)
        # Set via environment variables, e.g. STM32_VID=0x0483, STM32_PID=0x374B, STM32_SN=...
        self.stm32_sig = {
            "vid": os.environ.get("STM32_VID", "").strip(),
            "pid": os.environ.get("STM32_PID", "").strip(),
            "sn": os.environ.get("STM32_SN", "").strip(),
        }


        # widgets
        self.btn_connection = {}
        self.entry_connection = {}
        self.combo_connection = {}

        # groups 
        self.group_connection = [
            ("Refresh",    805,  20),
            ("Connect",    985,  20),
            ("Disconnect", 1165, 20),
        ]
        self.group_entries_connection = [
            ("loop",   625, 20, 170, 30, "Baud Rate"),
        ]
        self.group_combo_connection = [
            # Defaults requested: STM32 -> COM3, PiLink -> COM4
            ("port_name", 445, 20, 170, 30, ["COM3", "COM4", "COM5"], "COM3"),
            # Pi IP presets (like COM port history)
            ("pi_ip", 265, 20, 170, 30, ["192.168.0.116", "127.0.0.1"], "127.0.0.1"),
        ]

        # Persist last used Pi IP (similar to remembering last COM port)
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            self._pi_ip_store_path = os.path.join(base_dir, "pi_ip_last.txt")
        except Exception:
            self._pi_ip_store_path = None

    def _load_last_pi_ip(self) -> str:
        if not self._pi_ip_store_path:
            return ""
        try:
            with open(self._pi_ip_store_path, "r", encoding="utf-8") as f:
                return (f.read() or "").strip()
        except Exception:
            return ""

    def _save_last_pi_ip(self, ip: str):
        if not self._pi_ip_store_path:
            return
        try:
            with open(self._pi_ip_store_path, "w", encoding="utf-8") as f:
                f.write((ip or "").strip())
        except Exception:
            pass

    def build(self):
        # create widgets
        self.btn_connection = create_button_group(self.parent, self.group_connection, 170, 30)
        self.entry_connection = create_entry_group(self.parent, self.group_entries_connection)
        self.combo_connection = create_combobox_group(self.parent, self.group_combo_connection)

        # Pi IP combobox: restore last used value if available
        try:
            last_ip = self._load_last_pi_ip()
            if last_ip and "pi_ip" in self.combo_connection:
                # ensure last_ip is selectable; if not, prepend it
                cur_vals = list(self.combo_connection["pi_ip"].cget("values") or [])
                if last_ip not in cur_vals:
                    cur_vals = [last_ip] + cur_vals
                    self.combo_connection["pi_ip"].configure(values=cur_vals)
                self.combo_connection["pi_ip"].set(last_ip)
        except Exception:
            pass

        # bind commands 
        self.btn_connection["Refresh"].configure(command=self.refresh_ports)
        self.btn_connection["Connect"].configure(command=self.connect_all)
        self.btn_connection["Disconnect"].configure(command=self.disconnect_all)

        # ===== initial state =====
        # (AppUI sẽ ép state theo rule mỗi tick; đây chỉ là mặc định lúc build)
        self.btn_connection["Connect"].configure(state="normal")
        self.btn_connection["Disconnect"].configure(state="disabled")

        return self


    # ================= PORT AUTO-DETECT (VID/PID/SN) =================
    @staticmethod
    def _parse_hex_int(s: str):
        s = (s or "").strip().lower()
        if not s:
            return None
        try:
            if s.startswith("0x"):
                return int(s, 16)
            return int(s, 16) if all(c in "0123456789abcdef" for c in s) else int(s)
        except Exception:
            return None

    def _match_sig(self, port_info, sig: dict) -> bool:
        vid = self._parse_hex_int(sig.get("vid"))
        pid = self._parse_hex_int(sig.get("pid"))
        sn = (sig.get("sn") or "").strip()
        if vid is not None and port_info.vid != vid:
            return False
        if pid is not None and port_info.pid != pid:
            return False
        if sn and (getattr(port_info, "serial_number", None) != sn):
            return False
        return True

    def _detect_stm32_port(self, port_infos):
        # 1) exact signature match if provided
        if any(self.stm32_sig.values()):
            for p in port_infos:
                if self._match_sig(p, self.stm32_sig):
                    return p.device

        # 2) heuristic by description/manufacturer/product
        for p in port_infos:
            hay = " ".join([(p.description or ""), (p.manufacturer or ""), (p.product or "")]).lower()
            if ("stlink" in hay) or ("st-link" in hay) or ("stm" in hay and "usb" in hay):
                return p.device
        return None

    # ================= REFRESH =================
    def refresh_ports(self):
        port_infos = list(serial.tools.list_ports.comports())
        ports = [p.device for p in port_infos]
        if not ports:
            ports = ["(none)"]

        # Update STM32 port combobox (if present)
        for key in ("port_name",):
            if key in self.combo_connection:
                self.combo_connection[key].configure(values=ports)

        # Auto-select using VID/PID/SN if possible (fallback to heuristics)
        stm32_auto = self._detect_stm32_port(port_infos)

        if stm32_auto and "port_name" in self.combo_connection:
            self.combo_connection["port_name"].set(stm32_auto)
        else:
            # keep current selection if still available; otherwise default STM32 -> COM3 if present
            cur = self.combo_connection.get("port_name").get() if "port_name" in self.combo_connection else ""
            if (cur not in ports) and ("port_name" in self.combo_connection):
                self.combo_connection["port_name"].set("COM3" if "COM3" in ports else ports[0])

        self.log("Ports refreshed")

    # ================= CONNECT/DISCONNECT =================
    def connect_all(self):
        # Guard against accidental double/triple invocation from UI bindings
        if getattr(self, "_connecting", False):
            return
        self._connecting = True
        try:
            # ===== Connect STM32 =====
            stm_port = self.combo_connection.get("port_name").get().strip()
            try:
                stm_baud = int(self.entry_connection["loop"].get())
            except Exception:
                stm_baud = 115200
                self.entry_connection["loop"].delete(0, "end")
                self.entry_connection["loop"].insert(0, str(stm_baud))

            stm_ok, stm_msg = self.serial_mgr.connect(stm_port, stm_baud)
            if stm_ok:
                self.log(stm_msg)
            else:
                self.log("STM32 connect failed: " + stm_msg, "ERROR")

            # ===== Connect RasPi (optional) =====
            pi_ok = False
            if self.pi_connect_fn is not None and "pi_ip" in self.combo_connection:
                pi_ip = (self.combo_connection["pi_ip"].get() or "").strip()
                if pi_ip:
                    try:
                        pi_ok, pi_msg = self.pi_connect_fn(pi_ip, 9999)
                        # Use the same log style as the existing STM32 combobox flow
                        self.log(pi_msg or ("PiLink connected" if pi_ok else "PiLink connect failed"), "INFO" if pi_ok else "ERROR")
                        if pi_ok:
                            self._save_last_pi_ip(pi_ip)
                    except Exception as e:
                        self.log("PiLink connect failed: " + str(e), "ERROR")

            # ===== Update button states =====
            # Keep existing behavior: Connect disabled once STM32 connected.
            if stm_ok:
                self.btn_connection["Connect"].configure(state="disabled")
                self.btn_connection["Disconnect"].configure(state="normal")
            else:
                # If STM32 not connected but Pi connected, allow user to Disconnect
                if pi_ok:
                    self.btn_connection["Connect"].configure(state="normal")
                    self.btn_connection["Disconnect"].configure(state="normal")
                else:
                    self.btn_connection["Connect"].configure(state="normal")
                    self.btn_connection["Disconnect"].configure(state="disabled")
        finally:
            self._connecting = False

    def disconnect_all(self):
        # Disconnect STM32
        try:
            self.serial_mgr.disconnect()
        except Exception:
            pass

        # Disconnect RasPi (optional)
        if self.pi_disconnect_fn is not None:
            try:
                self.pi_disconnect_fn()
            except Exception:
                pass

        self.log("Disconnected")
        self.btn_connection["Connect"].configure(state="normal")
        self.btn_connection["Disconnect"].configure(state="disabled")

    # Backward-compatible aliases (old code expects these names)
    def connect_serial_v5(self):
        """Alias for connect_all() to keep older AppUI code working."""
        return self.connect_all()

    def disconnect_serial_v5(self):
        """Alias for disconnect_all() to keep older AppUI code working."""
        return self.disconnect_all()

