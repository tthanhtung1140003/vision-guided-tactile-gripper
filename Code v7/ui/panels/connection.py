import serial.tools.list_ports
from ui.widgets.figma import create_button_group, create_entry_group, create_combobox_group


class ConnectionPanel:
    def __init__(self, parent, serial_mgr, log_cb):
        self.parent = parent
        self.serial_mgr = serial_mgr
        self.log = log_cb  

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
            ("port_name", 445, 20, 170, 30, ["COM3", "COM4", "COM5"], "COM3"),
        ]

    def build(self):
        # create widgets
        self.btn_connection = create_button_group(self.parent, self.group_connection, 170, 30)
        self.entry_connection = create_entry_group(self.parent, self.group_entries_connection)
        self.combo_connection = create_combobox_group(self.parent, self.group_combo_connection)

        # bind commands 
        self.btn_connection["Refresh"].configure(command=self.refresh_ports)
        self.btn_connection["Connect"].configure(command=self.connect_serial_v5)
        self.btn_connection["Disconnect"].configure(command=self.disconnect_serial_v5)

        # ===== initial state =====
        # (AppUI sẽ ép state theo rule mỗi tick; đây chỉ là mặc định lúc build)
        self.btn_connection["Connect"].configure(state="normal")
        self.btn_connection["Disconnect"].configure(state="disabled")

        return self

    # ================= REFRESH =================
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["(none)"]
        self.combo_connection["port_name"].configure(values=ports)
        self.combo_connection["port_name"].set(ports[0])
        self.log("Ports refreshed")

    # ================= CONNECT/DISCONNECT =================
    def connect_serial_v5(self):
        port = self.combo_connection["port_name"].get()
        try:
            baud = int(self.entry_connection["loop"].get())
        except:
            baud = 115200
            self.entry_connection["loop"].delete(0, "end")
            self.entry_connection["loop"].insert(0, str(baud))

        ok, msg = self.serial_mgr.connect(port, baud)
        if ok:
            self.log(msg)
            self.btn_connection["Connect"].configure(state="disabled")
            self.btn_connection["Disconnect"].configure(state="normal")
        else:
            self.log("Connect failed: " + msg)

    def disconnect_serial_v5(self):
        self.serial_mgr.disconnect()
        self.log("Disconnected")
        self.btn_connection["Connect"].configure(state="normal")
        self.btn_connection["Disconnect"].configure(state="disabled")
