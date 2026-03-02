import customtkinter as ctk
from PIL import Image
from datetime import datetime
import time 
import threading
import os
from collections import deque

# Plot3D is heavy (matplotlib). Lazy-import inside _init_plot3d() to avoid blocking startup.
from ui.panels.slider_axis import SliderAxisPanel
from ui.panels.log import LogPanel
from ui.panels.connection import ConnectionPanel
from ui.panels.motion import MotionPanel
from ui.panels.paths import PathPanel
from ui.panels.laws import LawsPanel
from core.pi_link import PiLink

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
        # expose axis limits for MotionController clamp
        self.state.limits = self.SLIDER_MAX
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

        self._reset_pi_mode_state()

        # ===== Startup bootstrapping (reduce GUI freeze) =====
        self._ui_ready = False
        self._boot_tasks = []
        self._boot_index = 0
        self._loading_label = None
        self._plot_placeholder = None

        self._build_skeleton()
        self._setup_boot_tasks()
        # Build UI incrementally so the window stays responsive
        self.root.after(0, self._bootstrap_next)

    # ====================== Gantry STOP detect (for manual Approach_Done) ======================
    def _gantry_stopped(self) -> bool:
        """Return True if gantry is considered STOPPED.

        Goal: user can press Approach as soon as the gantry is actually stopped at target.
        We consider STOPPED if ANY of these holds consistently:
        1) Firmware state indicates idle/ready/stop (when available),
        2) Speed feedback (SPD) is below threshold,
        3) Position is stable (delta < eps) for N ticks (robust when SPD is missing/noisy).
        """
        # 1) Firmware state hint (most reliable when present)
        stopped_by_fw = False
        try:
            fw_state = str(getattr(self.state, "fw_state", "") or "").strip().lower()
            if any(k in fw_state for k in ("idle", "ready", "stop", "stopped", "hold")):
                stopped_by_fw = True
        except Exception:
            stopped_by_fw = False

        # 2) Speed feedback (SPD)
        stopped_by_speed = False
        try:
            spd = getattr(self.state, "speed", [0.0, 0.0, 0.0])
            v_eps = float(getattr(self, "_approach_stop_veps", 1.0))  # mm/s
            stopped_by_speed = (abs(spd[0]) < v_eps and abs(spd[1]) < v_eps and abs(spd[2]) < v_eps)
        except Exception:
            stopped_by_speed = False

        # 3) Position stability detector (fallback / jitter-tolerant)
        stopped_by_pos = False
        try:
            pos = getattr(self.state, "pos", [0.0, 0.0, 0.0])
            last = getattr(self, "_approach_last_pos", None)
            # default eps larger to tolerate encoder jitter/noise
            p_eps = float(getattr(self, "_approach_stop_poseps", 0.2))  # mm
            if last is None:
                self._approach_last_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
                self._approach_pos_confirm = 0
            else:
                dx = abs(float(pos[0]) - float(last[0]))
                dy = abs(float(pos[1]) - float(last[1]))
                dz = abs(float(pos[2]) - float(last[2]))
                if dx < p_eps and dy < p_eps and dz < p_eps:
                    self._approach_pos_confirm += 1
                else:
                    self._approach_pos_confirm = 0
                self._approach_last_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
            stopped_by_pos = (self._approach_pos_confirm >= int(getattr(self, "_approach_stop_ticks", 1)))
        except Exception:
            stopped_by_pos = False

        stopped = bool(stopped_by_fw or stopped_by_speed or stopped_by_pos)

        # Short confirm gate to avoid 1-tick glitches; default 1 tick for snappy UX
        if stopped:
            self._approach_stop_confirm += 1
        else:
            self._approach_stop_confirm = 0

        return self._approach_stop_confirm >= int(getattr(self, "_approach_stop_ticks", 1))

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


    # ====================== Incremental UI bootstrapping ======================
    def _build_skeleton(self):
        # bg frame + bg image
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        bg_path = os.path.join(base_dir, "BG.png")
        try:
            img = Image.open(bg_path)
        except Exception:
            img = None

        self.bg_frame = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.bg_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        if img is not None:
            bg_image = ctk.CTkImage(light_image=img, dark_image=img, size=(1366, 768))
            bg_label = ctk.CTkLabel(self.bg_frame, image=bg_image, text="")
            bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._bg_image = bg_image
            self._bg_label = bg_label

        # A small loading hint so users know the app is initializing
        self._loading_label = ctk.CTkLabel(
            self.bg_frame,
            text="Loading UI...",
            text_color="#333333"
        )
        self._loading_label.place(x=20, y=12)

        # Placeholder for plot area (matplotlib init is heavy)
        # NOTE: CustomTkinter requires width/height to be passed in the widget constructor,
        # not in the place() call.
        self._plot_placeholder = ctk.CTkFrame(
            self.bg_frame,
            fg_color="#FFFFFF",
            corner_radius=10,
            width=400,
            height=400,
        )
        self._plot_placeholder.place(x=430, y=320)
        ph_lbl = ctk.CTkLabel(self._plot_placeholder, text="Plot is loading…", text_color="#666666")
        ph_lbl.place(relx=0.5, rely=0.5, anchor="center")

    def _setup_boot_tasks(self):
        # Build light-weight panels first, postpone heavy plot3d
        self._boot_tasks = [
            self._build_slider_axis,
            self._build_log_panel,
            self._build_connection_panel,
            self._build_motion_panel,
            self._build_path_panel,
            self._build_laws_panel,
            self._finalize_boot,
        ]

    def _bootstrap_next(self):
        try:
            if self._boot_index >= len(self._boot_tasks):
                return
            task = self._boot_tasks[self._boot_index]
            self._boot_index += 1
            task()
        except Exception as e:
            # Don't hard-freeze the UI on boot errors; log if possible
            try:
                self.append_log(f"Boot step failed: {e}", "ERROR")
            except Exception:
                pass
        finally:
            if self._boot_index < len(self._boot_tasks):
                self.root.after(20, self._bootstrap_next)

    def _build_slider_axis(self):
        self.slider_axis_panel = SliderAxisPanel(self.bg_frame, self.slider_pos, self.SLIDER_MAX).build()
        self.slider_axis = self.slider_axis_panel.slider_axis

    def _build_log_panel(self):
        self.log_panel_obj = LogPanel(self.bg_frame).build()

    def _build_connection_panel(self):
        self.conn_panel = ConnectionPanel(
            self.bg_frame,
            self.serial_mgr,
            self.append_log,
            pi_connect_fn=self._connect_pi_link_from,
            pi_disconnect_fn=self._disconnect_pi_link,
        ).build()

        # Wrap connect/disconnect so we can run blocking work off the UI thread
        self.conn_panel.btn_connection["Connect"].configure(command=self._on_connect_clicked)
        self.conn_panel.btn_connection["Disconnect"].configure(command=self._on_disconnect_clicked)

    def _build_motion_panel(self):
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

        # Wrap stop/resume so UI locks immediately
        self.motion_panel.btn_motion["Stop"].configure(command=self._on_stop_clicked)
        self.motion_panel.btn_motion["resume"].configure(command=self._on_resume_clicked)

    def _build_path_panel(self):
        self.path_panel = PathPanel(self.bg_frame, self.state, self.path_engine, self.motion, self.append_log).build()
        self.path_panel.slider_pos = self.slider_pos
        self.path_panel.on_point_selected = self._on_path_point_selected

    def _build_laws_panel(self):
        self.laws_panel = LawsPanel(
            self.bg_frame,
            on_grasping_mode=self._on_grasping_mode_clicked,
            on_approach_done=self._on_approach_done_clicked,
            on_handover_mode=self._on_handover_mode_clicked,
            on_tracking_toggle=self._on_tracking_toggle_clicked,
        ).build()
        self._apply_laws_states(force=True)

    def _finalize_boot(self):
        # Enable/disable groups based on connection state
        self._apply_control_states(force=True)

        # UI is now ready: start ticking
        self._ui_ready = True
        if self._loading_label:
            try:
                self._loading_label.configure(text="Ready")
                self.root.after(800, lambda: self._loading_label.destroy() if self._loading_label else None)
            except Exception:
                pass

        # Defer plot initialization to keep the first render responsive
        self.root.after(3000, self._init_plot3d_safe)

        # Start the periodic UI loop
        self.root.after(100, self.ui_tick)

    def _init_plot3d_safe(self):
        # Lazy import matplotlib panels here
        try:
            from ui.panels.plot3d import Plot3DPanel, PlotControlsPanel
        except Exception as e:
            self.append_log(f"Plot import failed: {e}", "ERROR")
            return

        try:
            self.plot_panel = Plot3DPanel(parent=self.bg_frame, root=self.root).build()
            self.plot_controls = PlotControlsPanel(parent=self.bg_frame, slider_pos=self.slider_pos).build()
            self.slider_view = self.plot_controls.slider_view
            # Remove placeholder
            if self._plot_placeholder:
                self._plot_placeholder.destroy()
                self._plot_placeholder = None
        except Exception as e:
            self.append_log(f"Plot init failed: {e}", "ERROR")


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
        # Read UI fields in the UI thread
        try:
            stm_port = self.conn_panel.combo_connection.get("port_name").get().strip()
        except Exception:
            stm_port = ""
        try:
            stm_baud = int(self.conn_panel.entry_connection["loop"].get())
        except Exception:
            stm_baud = 115200
            try:
                self.conn_panel.entry_connection["loop"].delete(0, "end")
                self.conn_panel.entry_connection["loop"].insert(0, str(stm_baud))
            except Exception:
                pass

        pi_ip = ""
        try:
            if "pi_ip" in self.conn_panel.combo_connection:
                pi_ip = (self.conn_panel.combo_connection["pi_ip"].get() or "").strip()
        except Exception:
            pi_ip = ""

        # Optimistic UI state: disable Connect while connecting
        try:
            self._set_btn_state(self.conn_panel.btn_connection.get("Connect"), "disabled")
            self._set_btn_state(self.conn_panel.btn_connection.get("Disconnect"), "disabled")
        except Exception:
            pass

        def worker():
            stm_ok, stm_msg = (False, "unknown")
            pi_ok, pi_msg = (False, "")
            try:
                stm_ok, stm_msg = self.serial_mgr.connect(stm_port, stm_baud)
            except Exception as e:
                stm_ok, stm_msg = False, str(e)

            # Pi connect (optional) - TCP connect can block if unreachable, so keep short timeout
            if pi_ip and pi_ip.lower() not in ("rasp pi ip address", "rasp pi ip", "pi ip address"):
                try:
                    pi_ok, pi_msg = self._connect_pi_link_from(pi_ip, 9999)
                except Exception as e:
                    pi_ok, pi_msg = False, f"PiLink connect failed: {e}"

            def done():
                # Log results
                if stm_ok:
                    self.append_log(stm_msg or "STM32 connected", "INFO")
                    self._ui_forced_stop = False
                else:
                    self.append_log("STM32 connect failed: " + (stm_msg or ""), "ERROR")

                if pi_ip:
                    self.append_log(pi_msg or ("PiLink connected" if pi_ok else "PiLink connect failed"), "INFO" if pi_ok else "ERROR")

                # Update buttons similar to original behavior
                try:
                    if stm_ok:
                        self._set_btn_state(self.conn_panel.btn_connection.get("Connect"), "disabled")
                        self._set_btn_state(self.conn_panel.btn_connection.get("Disconnect"), "normal")
                    else:
                        # If STM32 not connected but Pi connected, allow Disconnect
                        self._set_btn_state(self.conn_panel.btn_connection.get("Connect"), "normal")
                        self._set_btn_state(self.conn_panel.btn_connection.get("Disconnect"), "normal" if pi_ok else "disabled")
                except Exception:
                    pass

                self._apply_control_states()
                self._apply_laws_states()

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnect_clicked(self):
        # Optimistic UI state
        try:
            self._set_btn_state(self.conn_panel.btn_connection.get("Connect"), "disabled")
            self._set_btn_state(self.conn_panel.btn_connection.get("Disconnect"), "disabled")
        except Exception:
            pass

        def worker():
            try:
                self.serial_mgr.disconnect(reason="UI_DISCONNECT")
            except Exception:
                pass
            try:
                self._disconnect_pi_link()
            except Exception:
                pass

            def done():
                self._reset_pi_mode_state()
                self._ui_forced_stop = False
                self.append_log("Disconnected", "INFO")
                try:
                    self._set_btn_state(self.conn_panel.btn_connection.get("Connect"), "normal")
                    self._set_btn_state(self.conn_panel.btn_connection.get("Disconnect"), "disabled")
                except Exception:
                    pass
                self._apply_control_states()
                self._apply_laws_states()

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop_clicked(self):
        self._ui_forced_stop = True
        self.motion_panel.stop_path()
        self._apply_control_states()

    def _on_resume_clicked(self):
        self.motion_panel.resume_v5()
        self._ui_forced_stop = False

        self._reset_pi_mode_state()

        self._apply_control_states()

    def _apply_control_states(self, force: bool = False):
        # NOTE:
        #   - Control buttons (Homing/Move/Stop/Resume/Path/Manual jog...) depend ONLY on STM32 connection.
        #   - Group Law 4 buttons depend on BOTH STM32 + RasPi connection (handled in _apply_laws_states).
        connected = bool(getattr(self.state, "connected", False))
        fw_state = getattr(self.state, "fw_state", None)

        SYS_STOPPED = 5
        SYS_ERROR = 6
        # NOTE: Firmware state codes vary across versions. Treat only explicit UI-forced stop or SYS_ERROR as 'halted'.
        halted = bool(self._ui_forced_stop or (fw_state == SYS_ERROR))

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
            # disable motion + path, but keep Laws enabled (so Pi-mode commands can still be tested/issued)
            self._set_group_state(motion_axis, "disabled")
            self._set_group_state(motion_btns, "disabled")
            self._set_group_state(path_btns, "disabled")
            # Keep laws enabled; specific enable/disable will be handled by _apply_laws_states()
            self._set_group_state(laws_btns, "normal")
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
        if not getattr(self, '_ui_ready', False):
            self.root.after(100, self.ui_tick)
            return
        self._flush_logs()
        # ===== Poll firmware status =====
        if getattr(self.state, "connected", False):
            now = time.monotonic()
            if now - self._last_status_poll >= self._status_poll_interval:
                self._last_status_poll = now
                self.serial_mgr.send("?")
        # ===== Handle PiLink messages =====
        self._handle_pi_messages()
        self._tracking_watchdog()
        self._approach_autoreset()
        self._auto_lift_done()

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

        if self.plot_panel is not None and self.plot_controls is not None:
            self.update_plot_3d()
            try:
                self.plot_controls.tick()
            except Exception:
                pass
        self.update_limit_pills()

        # keep buttons in sync with connection/state
        self._apply_control_states()

        self.root.after(100, self.ui_tick)



    # ====================== PiLink (TCP) ======================
    def _connect_pi_link_from(self, host: str, port: int):
        """Connect PiLink on given TCP host:port. Returns (ok, msg)."""
        self.pi_host = (host or '').strip()
        self.pi_port = int(port or 9999)
        if not self.pi_host:
            return False, 'empty host'
        try:
            if self.pi_link is None or (hasattr(self.pi_link, 'host') and self.pi_link.host != self.pi_host) or (hasattr(self.pi_link, 'port') and self.pi_link.port != self.pi_port):
                # recreate link if host/port changed
                self.pi_link = PiLink(self.pi_host, self.pi_port, on_rx_line=lambda s: None)
            self.pi_link.open()
            self.pi_connected = True
            # IMPORTANT: Do NOT log here. ConnectionPanel will log using the existing combobox style.
            return True, f"PiLink connected: {self.pi_host}:{self.pi_port}"
        except Exception as e:
            self.pi_connected = False
            return False, f"PiLink connect failed: {e}"

    def _connect_pi_link(self):
        if not self.pi_host:
            return
        try:
            if self.pi_link is None:
                self.pi_link = PiLink(self.pi_host, self.pi_port, on_rx_line=lambda s: None)
            self.pi_link.open()
            self.pi_connected = True
            self.append_log(f"PiLink connected on {self.pi_host}:{self.pi_port}", "INFO")
        except Exception as e:
            self.pi_connected = False
            self.append_log(f"PiLink connect failed: {e}", "ERROR")

    def _disconnect_pi_link(self):
        try:
            if self.pi_link:
                self.pi_link.close()
        except Exception:
            pass
        self.pi_connected = False

    def _reset_pi_mode_state(self):
        """Reset RasPi TCP link runtime + 4-mode state machine variables.

        IMPORTANT: Only call this on init / disconnect / resume (not inside ui_tick).
        """
        # ===== Pi TCP link (RasPi5) =====
        self.pi_link = None
        self.pi_host = os.environ.get('PI_TCP_HOST', '').strip()
        self.pi_port = int(os.environ.get('PI_TCP_PORT', '9999'))
        self.pi_connected = False

        # ===== 4-mode state machine =====
        # 4-button spec states
        # IDLE / GRASPING_PLANNING / GRASP_WAIT_GRASP_DONE / GRASP_POST_LIFT / HOLD / TRACKING / HANDOVER_WAIT_DONE
        self.mode_state = 'IDLE'
        self.grasp_ready = False  # after grasp done and mode done
        self.motion_lock = False  # lock gantry motion (safety) when Pi is grasping

        # Tracking step size (mm) per jog pulse. Pi sends one direction at a time (Move X+/Y-/...).
        # Tracking config (TVEL velocity mode)
        self.track_step_mm = float(os.environ.get('TRACK_STEP_MM', '1.0'))  # legacy, kept
        self.track_vel_mmps = float(os.environ.get('TRACK_VEL_MMPS', '1.0'))
        self._track_tvel_heartbeat = float(os.environ.get('TRACK_TVEL_HEARTBEAT_S', '0.20'))  # must be < firmware TVEL watchdog
        # For smoother continuous tracking, we emit smaller jog pulses at higher rate.
        # This reduces 'giật' between pulses while keeping overall direction latch behavior.
        self.track_pulse_mm = float(os.environ.get('TRACK_PULSE_MM', '0.4'))
        # If watchdog is too small (or 0), TRACKING will drop back to IDLE immediately.
        # Default to 1.0s and clamp to a sensible minimum.
        self.track_watchdog_s = float(os.environ.get('TRACK_WATCHDOG_S', '6.0'))
        if self.track_watchdog_s < 0.5:
            self.track_watchdog_s = 0.5
        self._last_track_cmd_time = 0.0
        self._last_track_send_time = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self._track_min_interval = float(os.environ.get('TRACK_MIN_INTERVAL', '0.03'))  # seconds between jog pulses

        # Tracking continuous loop scheduling (Tk after id)
        self._track_after_id = None
        self._track_hold_running = False
        self._track_hold_last_tick = 0.0
        self._track_hold_fail_count = 0

        # Continuous tracking hold (Pi sends one Move X+/Y-/Z+ and we keep jogging until Pi sends STOP)
        self._track_hold_axis = None   # "X"/"Y"/"Z"
        self._track_hold_sign = None   # "+" or "-"
        self._track_hold_active = False
        self._track_hold_running = False
        # Heartbeat for tracking hold loop (used to auto-recover if Tk after-callback stops due to an exception)
        self._track_hold_last_tick = 0.0
        self._track_hold_fail_count = 0

        # Approach detect
        # Manual approach confirm (no auto-arrival):
        # - First click: enter GRASP_WAIT_APPROACH
        # - Second click: if gantry STOPPED -> send Approach_Done
        # If user moves gantry after sending Approach_Done, GUI will auto-reset back to GRASP_WAIT_APPROACH.
        self._approach_sent = False
        self._approach_stop_veps = float(os.environ.get('APPROACH_STOP_VEPS', '1.0'))  # mm/s  # mm/s
        self._approach_stop_ticks = int(os.environ.get('APPROACH_STOP_TICKS', '1'))
        self._approach_stop_confirm = 0
        # Secondary stop detector by position stability (mm). Helps when SPD is not available or lags.
        self._approach_stop_poseps = float(os.environ.get('APPROACH_STOP_POSEPS', '0.2'))
        self._approach_last_pos = None
        self._approach_pos_confirm = 0

        # (legacy/unused) keep these so older env vars won't crash if referenced elsewhere
        self._approach_target = [0.0, 0.0, 0.0]
        self._approach_stable = 0
        self._approach_eps = float(os.environ.get('APPROACH_EPS_MM', '0.3'))

        # Lift after grasp
        self._lift_target = None
        self._lift_stable = 0
        self._lift_mm = float(os.environ.get('GRASP_LIFT_MM', '10.0'))

    def _pi_send(self, cmd: str, payload: str = "", require_ack: bool = False):
        if not self.pi_link or not self.pi_link.is_open():
            self.append_log("PiLink not connected", "ERROR")
            return False
        # Raw TCP text protocol: send a single command line.
        ok, _, _ = self.pi_link.send_cmd(cmd, payload, require_ack=require_ack)
        if not ok:
            self.append_log(f"Pi CMD failed: {cmd} {payload}".strip(), "ERROR")
            return False
        return True

    def _handle_pi_messages(self):
        if not self.pi_link or not self.pi_link.is_open():
            return
        msgs = self.pi_link.poll(50)
        for msg in msgs:
            # In raw TCP text protocol, Pi sends plain lines like:
            #   Grasp_done / Grasp_fail / Handover_done
            #   Move X+ / STOP
            line = (msg.raw or msg.payload or "").strip()

            # Log every received RasPi line (throttle repeated Move spam)
            try:
                if not hasattr(self, '_pi_rx_last'):
                    self._pi_rx_last = {'line': None, 'ts': 0.0, 'count': 0}
                now = time.monotonic()
                is_move = line.lower().startswith('move ') or line.lower().startswith('track_')
                same = (self._pi_rx_last['line'] == line)
                if (not is_move) or (not same) or ((now - float(self._pi_rx_last['ts'])) > 0.25):
                    if is_move and same and self._pi_rx_last.get('count', 0) > 0:
                        # summarize burst
                        self.append_log(f"Pi RX: {line} (x{self._pi_rx_last['count']+1})", "DEBUG")
                        self._pi_rx_last['count'] = 0
                    else:
                        self.append_log(f"Pi RX: {line}", "DEBUG")
                    self._pi_rx_last['line'] = line
                    self._pi_rx_last['ts'] = now
                else:
                    self._pi_rx_last['count'] = int(self._pi_rx_last.get('count', 0)) + 1
            except Exception:
                pass

            # --- GRASP events ---
            if line == "Grasp_done" or (msg.mode == "GRASP" and msg.payload == "Grasp_done"):
                self.append_log("Pi EVT: Grasp_done", "INFO")
                if self.mode_state == "GRASP_WAIT_GRASP_DONE":
                    # Start lift Z
                    self.mode_state = "GRASP_POST_LIFT"
                    self.motion_lock = False  # allow lift only
                    self._start_lift_after_grasp()

            if line == "Grasp_fail" or (msg.mode == "GRASP" and msg.payload == "Grasp_fail"):
                self.append_log("Pi EVT: Grasp_fail", "ERROR")
                # Reset to planning state
                if self.mode_state.startswith("GRASP"):
                    self.mode_state = "IDLE"
                    self.motion_lock = False
                    self._approach_sent = False
                    self._approach_stop_confirm = 0
                    self._apply_laws_states(force=True)

            # --- HANDOVER events ---
            if line == "Handover_done" or (msg.mode == "HANDOVER" and msg.payload == "Handover_done"):
                self.append_log("Pi EVT: Handover_done", "INFO")
                self.mode_state = "IDLE"
                self.grasp_ready = False
                self.motion_lock = False
                self._apply_laws_states()

            # --- TRACKING events ---
            # New raw tracking: "Move X+" / "STOP"
            if line.lower().startswith("move "):
                self._last_track_cmd_time = time.monotonic()
                self._handle_track_cmd(line)
            elif line in ("STOP", "Stop", "stop"):
                self._handle_track_stop(line)
            # Backward compatible tracking: Track_*
            if msg.mode == "TRACK":
                if (msg.payload or "").startswith("Track_"):
                    self._last_track_cmd_time = time.monotonic()
                    self._handle_track_cmd(msg.payload)
                elif (msg.payload or "").startswith("STOP_Track_") or (msg.payload or "").strip() in ("STOP","Stop","stop"):
                    self._handle_track_stop(msg.payload)

    # ====================== Laws buttons / state ======================
    def _apply_laws_states(self, force: bool = False):
        """
        Apply enable/disable rules for 4 buttons, based on:
          - connected (STM32)
          - grasp_ready
          - current mode_state
          - motion_lock
        """
        if not self.laws_panel:
            return

        # NOTE: Enable/disable must match "test 4 nút" behavior strictly.
        # States we care about here:
        #   - IDLE                 : enable Grasping_Mode + Tracking_Mode
        #   - GRASPING_PLANNING    : enable Approach_Done only
        #   - GRASP_WAIT_GRASP_DONE/GRASP_POST_LIFT : disable all
        #   - HOLD                 : enable Handover_Mode only
        #   - TRACKING             : enable Tracking_Mode (as toggle to Tracking_Mode_Done) only
        #   - HANDOVER_WAIT_DONE   : disable all

        connected = bool(getattr(self.state, "connected", False))
        pi_ok = bool(getattr(self, "pi_connected", False))
        # If only STM32 is connected but RasPi is not, keep ALL Group Law buttons disabled.
        connected = connected and pi_ok

        # default: all disabled
        grasp_en = False
        approach_en = False
        handover_en = False
        tracking_en = False

        if not connected:
            # keep all disabled when not connected
            pass
        elif self.mode_state == "IDLE":
            grasp_en = True
            tracking_en = True
        elif self.mode_state == "GRASPING_PLANNING":
            approach_en = True
        elif self.mode_state in ("GRASP_WAIT_GRASP_DONE", "GRASP_POST_LIFT"):
            # lock all
            pass
        elif self.mode_state == "HOLD":
            handover_en = True
        elif self.mode_state == "TRACKING":
            tracking_en = True
        elif self.mode_state == "HANDOVER_WAIT_DONE":
            # lock all
            pass
        else:
            # fallback: behave like IDLE when an unknown state appears
            grasp_en = True
            tracking_en = True

        self.laws_panel.set_enabled(grasping=grasp_en, approach=approach_en, handover=handover_en, tracking=tracking_en)
        # active highlight
        if self.mode_state.startswith("GRASP"):
            self.laws_panel.set_active("Grasping_Mode")
        elif self.mode_state == "TRACKING":
            # Do not change Tracking button visuals (single-state like Grasping)
            self.laws_panel.set_active(None)
        elif self.mode_state == "HANDOVER_WAIT_DONE":
            self.laws_panel.set_active("Handover_Mode")
        else:
            self.laws_panel.set_active(None)

    # ====================== New 4-button spec handlers ======================
    def _on_grasping_mode_clicked(self):
        self.append_log("[LAW] Click Grasping_Mode", "DEBUG")
        # Backward compatible: reuse existing grasp handler (stage 1)
        return self._on_grasp_clicked()

    def _on_approach_done_clicked(self):
        self.append_log("[LAW] Click Approach_Done", "DEBUG")
        # Trigger Approach_Done (stage 2) directly.
        if self.mode_state != "GRASPING_PLANNING":
            self.append_log("Approach_Done chỉ dùng sau khi bấm Grasping_Mode.", "WARN")
            return
        if not self._gantry_stopped():
            self.append_log("Gantry chưa dừng. Hãy STOP rồi bấm Approach_Done.", "WARN")
            return
        # Send Approach_Done
        if self._pi_send("Approach_Done"):
            self.append_log("Sent Approach_Done.", "INFO")
            self.mode_state = "GRASP_WAIT_GRASP_DONE"
            self.motion_lock = True
            self._approach_sent = True
            self._apply_laws_states(force=True)

    def _on_handover_mode_clicked(self):
        self.append_log("[LAW] Click Handover_Mode", "DEBUG")
        return self._on_handover_clicked()

    def _on_tracking_toggle_clicked(self):
        self.append_log("[LAW] Click Tracking_Mode toggle", "DEBUG")
        return self._on_tracking_clicked()


    # ====================== Legacy handlers (kept, now called by wrappers) ======================
    def _on_grasp_clicked(self):
        # New 4-button spec: this button ONLY sends Grasping_Mode and enters planning.
        if not getattr(self.state, "connected", False):
            self.append_log("Connect gantry first.", "ERROR")
            return
        if not (self.pi_link and self.pi_link.is_open()):
            self.append_log("PiLink not connected. Set PI_TCP_HOST and connect.", "ERROR")
            return

        if self.mode_state in ("GRASPING_PLANNING", "GRASP_WAIT_GRASP_DONE", "GRASP_POST_LIFT"):
            self.append_log("GRASP đang chạy. Hãy bấm Approach_Done để xác nhận tiếp cận.", "INFO")
            return

        if not self._pi_send("Grasping_Mode"):
            return

        self.mode_state = "GRASPING_PLANNING"
        self.grasp_ready = False
        self.motion_lock = False
        self._approach_sent = False
        self._approach_stop_confirm = 0
        self._approach_last_pos = None
        self._approach_pos_confirm = 0
        self.append_log("Sent Grasping_Mode. Di chuyển gantry đến vị trí và bấm Approach_Done.", "INFO")
        self._apply_laws_states()

    def _on_hold_clicked(self):
        if not self.grasp_ready:
            self.append_log("HOLD blocked: chưa ở trạng thái đang giữ (chưa Grasp_done).", "WARN")
            return
        if not (self.pi_link and self.pi_link.is_open()):
            self.append_log("PiLink not connected.", "ERROR")
            return
        self._pi_send("Hold_Mode")
        self.append_log("HOLD sent.", "INFO")

    def _on_handover_clicked(self):
        # Spec: chỉ được handover khi đang HOLD (đã Grasp_done + lift xong)
        if not self.grasp_ready:
            self.append_log("Handover blocked: chưa HOLD (hãy Grasp_done trước).", "WARN")
            return
        if self.motion_lock:
            self.append_log("Handover blocked: motion_lock.", "WARN")
            return
        if not (self.pi_link and self.pi_link.is_open()):
            self.append_log("PiLink not connected.", "ERROR")
            return

        if not self._pi_send("Handover_Mode"):
            return
        # disable hold immediately
        self.mode_state = "HANDOVER_WAIT_DONE"
        self.append_log("HANDOVER started: waiting Handover_done.", "INFO")
        self._apply_laws_states()

    def _on_tracking_clicked(self):
        if self.motion_lock:
            self.append_log("Blocked: motion_lock", "WARN")
            return
        if not getattr(self.state, "connected", False):
            self.append_log("Connect gantry first.", "ERROR")
            return
        if not (self.pi_link and self.pi_link.is_open()):
            self.append_log("PiLink not connected.", "ERROR")
            return

        # Toggle tracking: Tracking_Mode <-> Tracking_Mode_Done
        if self.mode_state == "TRACKING":
            if self._pi_send("Tracking_Mode_Done"):
                try:
                    self.motion.track_stop()
                except Exception:
                    try:
                        self.motion.stop()
                    except Exception:
                        pass
                self.mode_state = "IDLE"
                try:
                    self.state.estimate_pos = False
                except Exception:
                    pass
                self._track_hold_clear()
                self._track_cancel_loop()
                self.append_log("Sent Tracking_Mode_Done.", "INFO")
                self._apply_laws_states(force=True)
            return

        if self._pi_send("Tracking_Mode"):
            self.mode_state = "TRACKING"
            self._last_track_cmd_time = time.monotonic()
            self._last_track_send_time = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
            try:
                self.state.estimate_pos = True
            except Exception:
                pass
            # keep loop alive so later Move cmds always work
            self._track_ensure_loop()
            self.append_log("TRACKING started.", "INFO")
            self._apply_laws_states(force=True)
            return

    # ====================== Manual Approach_Done helpers ======================
    def _approach_autoreset(self):
        """(Legacy) Auto-reset if gantry moves unexpectedly after Approach_Done."""
        if self.mode_state != "GRASP_WAIT_GRASP_DONE":
            return
        if not self._approach_sent:
            return
        # If gantry is not stopped anymore => user is repositioning
        if not self._gantry_stopped():
            self._approach_sent = False
            self._approach_stop_confirm = 0
            self._approach_last_pos = None
            self._approach_pos_confirm = 0
            self.motion_lock = False
            self.mode_state = "GRASPING_PLANNING"
            self.append_log("Approach_Done reset (gantry moved). Bấm Approach_Done lại khi đã STOP.", "INFO")
            self._apply_laws_states()

    # ====================== Lift after grasp ======================
    def _start_lift_after_grasp(self):
        # Lower Z by _lift_mm using existing jog step-jog (mm)
        try:
            z_now = float(self.state.pos[2])
            if z_now < float(self._lift_mm):
                # If Z is already low (< lift_mm), skip lowering to avoid going below 0 / mechanical limit
                self.append_log(f"Z hiện tại ({z_now:.2f}mm) < {self._lift_mm:.2f}mm, bỏ qua hạ Z.", "INFO")
                # Notify Pi grasping done immediately
                if self._pi_send("Grasping_Mode_Done"):
                    self.append_log("Sent Grasping_Mode_Done.", "INFO")
                self.mode_state = "HOLD"
                self.motion_lock = False
                self.grasp_ready = True
                self._lift_target = None
                self._apply_laws_states()
                return

            # target is relative to current target_pos (or current pos)
            z_target = float(self.state.pos[2]) - float(self._lift_mm)
            self._lift_target = [self.state.pos[0], self.state.pos[1], z_target]
            self._lift_stable = 0
            self.motion.move_abs(self.state.pos[0], self.state.pos[1], z_target)
            self.append_log(f"Lowering Z by {self._lift_mm}mm...", "INFO")
        except Exception as e:
            self.append_log(f"Lift start failed: {e}", "ERROR")
            self._lift_target = None

    def _auto_lift_done(self):
        if self.mode_state != "GRASP_POST_LIFT":
            return
        if not self._lift_target:
            return
        pos = self.state.pos
        tgt = self._lift_target
        eps = self._approach_eps
        arrived = (abs(pos[2] - tgt[2]) <= eps)
        if arrived:
            self._lift_stable += 1
        else:
            self._lift_stable = 0
        if self._lift_stable >= 3:
            # Notify Pi grasping done
            if self._pi_send("Grasping_Mode_Done"):
                self.append_log("Sent Grasping_Mode_Done.", "INFO")
            
            self.mode_state = "HOLD"
            self.motion_lock = False
            self.grasp_ready = True
            self._lift_target = None
            self._apply_laws_states()

    # ====================== Tracking mapping (step-jog by mm) ======================
    
    def _track_hold_set(self, axis: str, sign: str):
        axis = (axis or "").upper()
        sign = "+" if sign == "+" else "-"
        if axis not in ("X", "Y", "Z"):
            return
        self._track_hold_axis = axis
        self._track_hold_sign = sign
        self._track_hold_active = True
        self._last_track_cmd_time = time.monotonic()

        # Always ensure loop is running (robust restart)
        self._track_ensure_loop()

    def _track_cancel_loop(self):
        """Cancel Tk after loop if scheduled."""
        try:
            if self._track_after_id is not None:
                self.root.after_cancel(self._track_after_id)
        except Exception:
            pass
        self._track_after_id = None
        self._track_hold_running = False

    def _track_ensure_loop(self):
        """Ensure the tracking loop is alive; restart if it died."""
        now = time.monotonic()
        stale = (self._track_hold_last_tick and (now - self._track_hold_last_tick) > max(0.3, self._track_min_interval * 6))
        if (not self._track_hold_running) or stale or (self._track_after_id is None):
            self._track_cancel_loop()
            self._track_hold_fail_count = 0
            self._track_hold_running = True
            self._track_after_id = self.root.after(0, self._track_hold_loop)
    def _track_hold_clear(self):
        self._track_hold_active = False
        self._track_hold_axis = None
        self._track_hold_sign = None

    def _track_hold_loop(self):
        """Tk after-loop for continuous tracking.

        Important: this MUST never die silently. If an exception happens inside,
        we log it and keep rescheduling so Tracking can continue for subsequent commands.
        """
        # heartbeat
        self._track_hold_last_tick = time.monotonic()

        if self.mode_state != "TRACKING":
            self._track_cancel_loop()
            return

        try:

                    if self.motion_lock:
                        # Keep heartbeat running even if motion is temporarily locked
                        pass

                    # Compute velocity command (single-axis hold)
                    vx = vy = vz = 0.0
                    if self._track_hold_active and self._track_hold_axis and (not self.motion_lock):
                        axis = self._track_hold_axis
                        sign = self._track_hold_sign or "+"
                        v = float(getattr(self, 'track_vel_mmps', 1.0))
                        v = abs(v)
                        if sign == "-":
                            v = -v
                        if axis == "X":
                            vx = v
                        elif axis == "Y":
                            vy = v
                        elif axis == "Z":
                            vz = v

                        # Soft-limit safety: clamp velocity to 0 at boundary (DO NOT issue STOP)
                        try:
                            lim = getattr(self.state, "limits", None) or {}
                            idx = "XYZ".index(axis)
                            vmax = float(lim.get(axis, 0.0)) if axis in lim else None
                            pos = float(getattr(self.state, 'pos', [0,0,0])[idx])
                            eps = 1e-3
                            hit = False
                            if sign == "+" and vmax is not None and pos >= (vmax - eps):
                                hit = True
                            if sign == "-" and pos <= (0.0 + eps):
                                hit = True
                            if hit:
                                # stop only this hold direction; keep TRACKING mode alive
                                self._track_hold_clear()
                                vx = vy = vz = 0.0
                                self.append_log(f"TRACK: hit soft limit on {axis}{sign} -> TSTOP", "WARN")
                                try:
                                    self.motion.track_stop()
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    # Heartbeat to firmware TVEL watchdog (<= 500ms on firmware)
                    now = time.monotonic()
                    hb = float(getattr(self, "_track_tvel_heartbeat", 0.20))
                    if (now - float(getattr(self, "_track_last_tvel_ts", 0.0))) >= max(0.05, hb):
                        self._track_last_tvel_ts = now
                        # If no active hold, we still can send zero TVEL occasionally (keeps mode consistent)
                        try:
                            self.motion.track_set_vel(vx, vy, vz)
                        except Exception:
                            pass
        except Exception as e:
            self._track_hold_fail_count += 1
            self.append_log(f"TRACK hold-loop error: {e}", "ERROR")
            # If errors keep happening, drop active hold but keep TRACKING mode alive
            if self._track_hold_fail_count >= 3:
                self._track_hold_clear()
        finally:
            # Always reschedule while in TRACKING
            if self.mode_state == "TRACKING":
                # Keep one scheduled callback id for robust cancellation/restart
                self._track_after_id = self.root.after(int(self._track_min_interval * 1000), self._track_hold_loop)

    def _handle_track_cmd(self, payload: str):
        # In TRACKING mode, Pi sends ONE direction command (e.g. "Move X+"),
        # and we keep moving continuously in that direction until Pi sends STOP
        # (or the user toggles Tracking off).
        if self.mode_state != "TRACKING":
            return
        payload = (payload or "").strip()
        low = payload.lower()

        axis = ""
        sign = ""
        if low.startswith("track_"):
            try:
                _, axisdir = payload.split("_", 1)  # X+
                axis = axisdir[0].upper()
                sign = axisdir[1]
            except Exception:
                return
        elif low.startswith("move "):
            # e.g. "Move X+" or "move x+"
            parts = payload.split()
            if len(parts) >= 2:
                axisdir = parts[1].strip()
                if len(axisdir) >= 2:
                    axis = axisdir[0].upper()
                    sign = axisdir[1]
        else:
            return

        if axis not in ("X", "Y", "Z"):
            return
        if sign not in ("+", "-"):
            return

        # Start/refresh continuous hold in one axis only
        self._track_hold_set(axis, sign)

    def _handle_track_stop(self, payload: str):
        # STOP from Pi: stop motion but KEEP TRACKING enabled.
        # User must press Tracking again to exit Tracking mode.
        if self.mode_state == "TRACKING":
            self._track_hold_clear()
            try:
                self.motion.track_stop()
            except Exception:
                # fallback
                self.motion.stop()
            self.append_log("TRACK: Pi STOP -> motion STOP (still TRACKING).", "INFO")
            # Keep loop alive (waiting for next Move)
            self._track_ensure_loop()

    def _tracking_watchdog(self):
        # Tracking should NOT auto-exit due to watchdog.
        # In continuous-hold mode, a single "Move X+/Y-/Z+" should keep the gantry moving
        # until we receive STOP (from Pi) or the user toggles Tracking off.
        # Therefore, watchdog is only a *safety stop* when NO hold is active (i.e. we're idle in TRACKING).
        if self.mode_state != "TRACKING":
            return
        if self.motion_lock:
            return
        # If we're currently holding a direction, do NOT watchdog-stop it.
        if getattr(self, "_track_hold_active", False):
            return

        now = time.monotonic()
        if not self._last_track_cmd_time:
            self._last_track_cmd_time = now
            return
        if (now - self._last_track_cmd_time) > self.track_watchdog_s:
            # watchdog disabled: only log, do NOT stop motion, do NOT exit TRACKING
            self._last_track_cmd_time = now
            self.append_log("TRACK watchdog: no cmd (log only, no STOP)", "WARN")