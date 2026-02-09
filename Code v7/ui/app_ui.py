import customtkinter as ctk
from PIL import Image
from datetime import datetime
import time 
import threading
from collections import deque

from ui.panels.plot3d import Plot3DPanel, PlotControlsPanel
from ui.panels.slider_axis import SliderAxisPanel
from ui.panels.log import LogPanel
from ui.panels.connection import ConnectionPanel
from ui.panels.motion import MotionPanel
from ui.panels.paths import PathPanel
from ui.panels.laws import LawsPanel

class AppUI:
    def __init__(self, root, state, serial_mgr, motion, path_engine,
                 *,
                 slider_pos, slider_max, entry_editing, entry_dirty, limit_eps, last_limit_state):
        self.root = root
        self.state = state
        self.serial_mgr = serial_mgr
        self.motion = motion
        self.path_engine = path_engine

        self.slider_pos = slider_pos
        self.SLIDER_MAX = slider_max
        self.entry_editing = entry_editing
        self.entry_dirty = entry_dirty
        self.LIMIT_EPS = limit_eps
        self._last_limit_state = last_limit_state

        self.bg_frame = None
        self.log_panel_obj = None
        self.plot_panel = None
        self.plot_controls = None
        self.slider_axis_panel = None
        self.slider_axis = None
        self.slider_view = None

        self.conn_panel = None
        self.motion_panel = None
        self.path_panel = None
        self.laws_panel = None

        self.pill_groups = None
        self.entry_control = None
        self.labels_status = None
        self.labels_target = None
        self.labels_speed = None
        # ===== status polling =====
        self._last_status_poll = 0.0
        # 10Hz để thấy tọa độ cập nhật khi đang di chuyển
        self._status_poll_interval = 0.1
        # =====  lag UI =====
        self._log_q = deque()
        self._log_lock = threading.Lock()
        self._log_flush_max = 30

        # ===== UI stop latch =====
        self._ui_forced_stop = False

        self._build()
        self.root.after(100, self.ui_tick)

    def append_log(self, msg: str, tag: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        with self._log_lock:
            self._log_q.append((msg, tag, ts))
            if len(self._log_q) > 2000:
                for _ in range(200):
                    if self._log_q:
                        self._log_q.popleft()

    def _flush_logs(self):
        batch = []
        with self._log_lock:
            for _ in range(self._log_flush_max):
                if not self._log_q:
                    break
                batch.append(self._log_q.popleft())
        for msg, tag, ts in batch:
            self.log_panel_obj.append(msg, tag, timestamp=ts)

    def _build(self):
        # bg frame + bg image
        img = Image.open("BG.png")
        self.bg_frame = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.bg_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        bg_image = ctk.CTkImage(light_image=img, dark_image=img, size=(1366, 768))
        bg_label = ctk.CTkLabel(self.bg_frame, image=bg_image, text="")
        bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._bg_image = bg_image
        self._bg_label = bg_label
        # panels
        self.slider_axis_panel = SliderAxisPanel(self.bg_frame, self.slider_pos, self.SLIDER_MAX).build()
        self.slider_axis = self.slider_axis_panel.slider_axis

        self.plot_panel = Plot3DPanel(parent=self.bg_frame, root=self.root).build()
        self.plot_controls = PlotControlsPanel(parent=self.bg_frame, slider_pos=self.slider_pos).build()
        self.slider_view = self.plot_controls.slider_view

        self.log_panel_obj = LogPanel(self.bg_frame).build()

        self.conn_panel = ConnectionPanel(self.bg_frame, self.serial_mgr, self.append_log).build()

        self.motion_panel = MotionPanel(
            parent=self.bg_frame,
            state=self.state,
            motion=self.motion,
            path_engine=self.path_engine,
            log_cb=self.append_log,
            slider_max=self.SLIDER_MAX,
            slider_pos=self.slider_pos,
            slider_axis=self.slider_axis,
            entry_editing=self.entry_editing,
            entry_dirty=self.entry_dirty,
        ).build()

        self.pill_groups = self.motion_panel.pill_groups
        self.entry_control = self.motion_panel.entry_control
        self.labels_status = self.motion_panel.labels_status
        self.labels_target = self.motion_panel.labels_target
        self.labels_speed  = self.motion_panel.labels_speed
        self.path_panel = PathPanel(self.bg_frame, self.state, self.path_engine, self.motion, self.append_log).build()
        self.path_panel.slider_pos = self.slider_pos
        self.path_panel.on_point_selected = self._on_path_point_selected

        self.laws_panel = LawsPanel(self.bg_frame).build()

        # ===== ONLY ADD: UI control state management =====
        # Wrap connect/disconnect so rules are enforced
        self.conn_panel.btn_connection["Connect"].configure(command=self._on_connect_clicked)
        self.conn_panel.btn_connection["Disconnect"].configure(command=self._on_disconnect_clicked)

        # Wrap stop/resume so UI locks immediately
        self.motion_panel.btn_motion["Stop"].configure(command=self._on_stop_clicked)
        self.motion_panel.btn_motion["resume"].configure(command=self._on_resume_clicked)

        # Apply initial state (Connect only)
        self._apply_control_states(force=True)

    def _on_path_point_selected(self, idx, pt: dict):
        if self.path_engine.is_running():
            return
        try:
            x = float(pt.get("x", 0.0))
            y = float(pt.get("y", 0.0))
            z = float(pt.get("z", 0.0))
        except Exception:
            self.append_log("Selected point has invalid coordinates", "ERROR")
            return
        # Clamp theo workspace của GUI
        x = max(0.0, min(x, self.SLIDER_MAX["X"]))
        y = max(0.0, min(y, self.SLIDER_MAX["Y"]))
        z = max(0.0, min(z, self.SLIDER_MAX["Z"]))
        # 1) Đổ vào entry XC/YC/ZC
        eX = self.motion_panel.entry_control["XC"]
        eY = self.motion_panel.entry_control["YC"]
        eZ = self.motion_panel.entry_control["ZC"]

        eX.delete(0, "end"); eX.insert(0, f"{x:.3f}")
        eY.delete(0, "end"); eY.insert(0, f"{y:.3f}")
        eZ.delete(0, "end"); eZ.insert(0, f"{z:.3f}")
        # reset dirty để Move dùng luôn
        self.entry_dirty["XC"] = False
        self.entry_dirty["YC"] = False
        self.entry_dirty["ZC"] = False
        # 2) (Tuỳ chọn nhưng nên có) Sync slider để user thấy target mới
        self.slider_pos["X"] = x
        self.slider_pos["Y"] = y
        self.slider_pos["Z"] = z
        self.slider_axis["X"].set(x)
        self.slider_axis["Y"].set(y)
        self.slider_axis["Z"].set(z)

        name = pt.get("name", f"#{idx}")
        self.append_log(f"Selected point {name}: loaded to target XC/YC/ZC (press Move to go)", "INFO")
    # ====== limit pills ======
    def is_at_min(self, axis):
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        return abs(self.state.pos[idx] - 0.0) <= self.LIMIT_EPS

    def is_at_max(self, axis):
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        return abs(self.state.pos[idx] - self.SLIDER_MAX[axis]) <= self.LIMIT_EPS

    def update_limit_pills(self):
        pills = self.pill_groups["log"]

        def show_pill(index, x, y):
            pills[index].place(x=x, y=y)
        # X
        st = "MIN" if self.is_at_min("X") else "MAX" if self.is_at_max("X") else None
        if st != self._last_limit_state["X"]:
            pills[0].place_forget()
            pills[1].place_forget()
            if st == "MIN":
                show_pill(0, 275, 80)
            elif st == "MAX":
                show_pill(1, 275, 120)
            self._last_limit_state["X"] = st
        # Y
        st = "MIN" if self.is_at_min("Y") else "MAX" if self.is_at_max("Y") else None
        if st != self._last_limit_state["Y"]:
            pills[2].place_forget()
            pills[3].place_forget()
            if st == "MIN":
                show_pill(2, 572, 80)
            elif st == "MAX":
                show_pill(3, 572, 120)
            self._last_limit_state["Y"] = st
        # Z
        st = "MIN" if self.is_at_min("Z") else "MAX" if self.is_at_max("Z") else None
        if st != self._last_limit_state["Z"]:
            pills[4].place_forget()
            pills[5].place_forget()
            if st == "MIN":
                show_pill(4, 869, 80)
            elif st == "MAX":
                show_pill(5, 869, 120)
            self._last_limit_state["Z"] = st

    def update_entry_if_not_editing(self, key, entry, value):
        if self.entry_editing.get(key) or self.entry_dirty.get(key):
            return
        entry.delete(0, "end")
        entry.insert(0, f"{value:.3f}")

    def update_plot_3d(self):
        self.plot_panel.update(
            state=self.state,
            slider_pos=self.slider_pos,
            slider_view=self.slider_view,
            slider_max=self.SLIDER_MAX,
        )

    # ===== ONLY ADD: UI enable/disable rules =====
    def _set_btn_state(self, btn, state: str):
        try:
            btn.configure(state=state)
        except Exception:
            pass

    def _set_group_state(self, btn_dict, state: str, *, skip_keys=None):
        if not btn_dict:
            return
        skip_keys = set(skip_keys or [])
        for k, b in btn_dict.items():
            if k in skip_keys:
                continue
            self._set_btn_state(b, state)

    def _on_connect_clicked(self):
        self.conn_panel.connect_serial_v5()
        if getattr(self.state, "connected", False):
            self._ui_forced_stop = False
        self._apply_control_states()

    def _on_disconnect_clicked(self):
        self.conn_panel.disconnect_serial_v5()
        self._ui_forced_stop = False
        self._apply_control_states()

    def _on_stop_clicked(self):
        self._ui_forced_stop = True
        self.motion_panel.stop_path()
        self._apply_control_states()

    def _on_resume_clicked(self):
        self.motion_panel.resume_v5()
        self._ui_forced_stop = False
        self._apply_control_states()

    def _apply_control_states(self, force: bool = False):
        connected = bool(getattr(self.state, "connected", False))
        fw_state = getattr(self.state, "fw_state", None)

        SYS_STOPPED = 5
        SYS_ERROR = 6
        halted = bool(self._ui_forced_stop or (fw_state in (SYS_STOPPED, SYS_ERROR)))

        conn_btns = getattr(self.conn_panel, "btn_connection", {})
        if conn_btns:
            if connected:
                self._set_btn_state(conn_btns.get("Connect"), "disabled")
                self._set_btn_state(conn_btns.get("Disconnect"), "normal")
                # Refresh: normal when connected & not halted
                if "Refresh" in conn_btns:
                    self._set_btn_state(conn_btns["Refresh"], "disabled" if halted else "normal")
            else:
                # Not connected: ONLY Connect enabled
                self._set_btn_state(conn_btns.get("Connect"), "normal")
                self._set_btn_state(conn_btns.get("Disconnect"), "disabled")
                if "Refresh" in conn_btns:
                    self._set_btn_state(conn_btns["Refresh"], "disabled")
                halted = False
                self._ui_forced_stop = False

        motion_axis = getattr(self.motion_panel, "btn_axis", {})
        motion_btns = getattr(self.motion_panel, "btn_motion", {})
        path_btns = getattr(self.path_panel, "btn_program", {})
        laws_btns = getattr(self.laws_panel, "btn_law", {})

        if not connected:
            self._set_group_state(motion_axis, "disabled")
            self._set_group_state(motion_btns, "disabled")
            self._set_group_state(path_btns, "disabled")
            self._set_group_state(laws_btns, "disabled")
            return

        if halted:
            # disable all
            self._set_group_state(motion_axis, "disabled")
            self._set_group_state(motion_btns, "disabled")
            self._set_group_state(path_btns, "disabled")
            self._set_group_state(laws_btns, "disabled")
            # enable Resume only
            if motion_btns and "resume" in motion_btns:
                self._set_btn_state(motion_btns["resume"], "normal")
            return
        # connected & normal: enable all, resume disabled
        self._set_group_state(motion_axis, "normal")
        self._set_group_state(motion_btns, "normal")
        self._set_group_state(path_btns, "normal")
        self._set_group_state(laws_btns, "normal")
        if motion_btns and "resume" in motion_btns:
            self._set_btn_state(motion_btns["resume"], "disabled")
    
    def ui_tick(self):
        self._flush_logs()
        # ===== Poll firmware status =====
        if getattr(self.state, "connected", False):
            now = time.monotonic()
            if now - self._last_status_poll >= self._status_poll_interval:
                self._last_status_poll = now
                self.serial_mgr.send("?")
        # ===== Update UI from feedback state.pos =====
        self.labels_status["X"].configure(text=f"{self.state.pos[0]:.2f}")
        self.labels_status["Y"].configure(text=f"{self.state.pos[1]:.2f}")
        self.labels_status["Z"].configure(text=f"{self.state.pos[2]:.2f}")

        # ===== Update speed labels (mm/s) =====
        if self.labels_speed and hasattr(self.state, "speed"):
            self.labels_speed["speedX"].configure(text=f"{self.state.speed[0]:.2f}")
            self.labels_speed["speedY"].configure(text=f"{self.state.speed[1]:.2f}")
            self.labels_speed["speedZ"].configure(text=f"{self.state.speed[2]:.2f}")

        # ===== update TARGET labels =====
        if self.labels_target and hasattr(self.state, "target_pos"):
            self.labels_target["targetX"].configure(text=f"{self.state.target_pos[0]:.2f}")
            self.labels_target["targetY"].configure(text=f"{self.state.target_pos[1]:.2f}")
            self.labels_target["targetZ"].configure(text=f"{self.state.target_pos[2]:.2f}")

        self.update_entry_if_not_editing("XC", self.entry_control["XC"], self.state.pos[0])
        self.update_entry_if_not_editing("YC", self.entry_control["YC"], self.state.pos[1])
        self.update_entry_if_not_editing("ZC", self.entry_control["ZC"], self.state.pos[2])

        self.update_plot_3d()
        self.update_limit_pills()
        self.plot_controls.tick()

        # keep buttons in sync with connection/state
        self._apply_control_states()

        self.root.after(100, self.ui_tick)
