from ui.widgets.figma import (
    create_pill_group_set,
    create_button_group,
    create_entry_group,
    create_label_group,
)

class MotionPanel:
    def __init__(self, parent, state, motion, path_engine, log_cb,
                 *,
                 slider_max,
                 slider_pos,
                 slider_axis,
                 entry_editing,
                 entry_dirty):
        self.parent = parent
        self.state = state
        self.motion = motion
        self.path_engine = path_engine
        self.log = log_cb

        self.SLIDER_MAX = slider_max
        self.slider_pos = slider_pos
        self.slider_axis = slider_axis
        self.entry_editing = entry_editing
        self.entry_dirty = entry_dirty

        self.pill_groups = None
        self.btn_axis = {}
        self.btn_motion = {}
        self.entry_settings = {}
        self.entry_control = {}
        self.labels_status = {}
        self.labels_target = {}
        self.labels_speed = {}

        self.group_pill = [
            ("log", 275,  80, 20, 50, "#a1e887"),
            ("log", 275, 120, 20, 50, "#a1e887"),
            ("log", 572,  80, 20, 50, "#a1e887"),
            ("log", 572, 120, 20, 50, "#a1e887"),
            ("log", 869,  80, 20, 50, "#a1e887"),
            ("log", 869, 120, 20, 50, "#a1e887"),
        ]

        self.group_axis = [
            ("X+", 925, 301),
            ("Y+", 1065,301),
            ("Z+", 1205,301),
            ("X-", 925, 345),
            ("Y-", 1065,345),
            ("Z-", 1205,345),
        ]
        self.group_motion = [
            ("Homing", 292, 539),
            ("Move",   292, 584),
            ("Stop",   292, 629),
            ("resume", 292, 674),
        ]

        self.group_entry_settings = [
            ("Step", 1205, 119, 130, 30, "Step"),
        ]
        self.group_entries_control = [
            ("XC",   925,  257, 130, 30, "XC"),
            ("YC",   1065, 257, 130, 30, "YC"),
            ("ZC",   1205, 257, 130, 30, "ZC"),
        ]

        self.group_labels_status = [
            ("X",   30, 105, 80, 50, 48, "0.00"),
            ("Y",  327, 105, 80, 50, 48, "0.00"),
            ("Z",  624, 105, 80, 50, 48, "0.00"),
        ]
        self.group_labels_target = [
            ("targetX", 134, 77, 80, 30, 20, "0.00"),
            ("targetY", 431, 77, 80, 30, 20, "0.00"),
            ("targetZ", 728, 77, 80, 30, 20, "0.00"),
        ]
        self.group_labels_speed = [
            ("speedX",   925, 203, 80, 30, 20, "0.00"),
            ("speedY",  1065, 203, 80, 30, 20, "0.00"),
            ("speedZ",  1205, 203, 80, 30, 20, "0.00"),
        ]

    def build(self):
        # pills
        self.pill_groups = create_pill_group_set(self.parent, self.group_pill)
        for pill in self.pill_groups.get("log", []):
            pill.place_forget()

        # labels
        self.labels_status = create_label_group(self.parent, self.group_labels_status)
        self.labels_target = create_label_group(self.parent, self.group_labels_target)
        self.labels_speed  = create_label_group(self.parent, self.group_labels_speed)

        # entries
        self.entry_settings = create_entry_group(self.parent, self.group_entry_settings)
        self.entry_settings["Step"].insert(0, "10.0")

        self.entry_control = create_entry_group(self.parent, self.group_entries_control)
        self._bind_entry_focus_and_dirty()

        # buttons
        self.btn_axis = create_button_group(self.parent, self.group_axis, 130, 30)
        self.btn_axis["X+"].configure(command=lambda: self.jog("X", +1))
        self.btn_axis["X-"].configure(command=lambda: self.jog("X", -1))
        self.btn_axis["Y+"].configure(command=lambda: self.jog("Y", +1))
        self.btn_axis["Y-"].configure(command=lambda: self.jog("Y", -1))
        self.btn_axis["Z+"].configure(command=lambda: self.jog("Z", +1))
        self.btn_axis["Z-"].configure(command=lambda: self.jog("Z", -1))

        self.btn_motion = create_button_group(self.parent, self.group_motion, 120, 35)
        self.btn_motion["Homing"].configure(command=self.homing_v5)
        self.btn_motion["Move"].configure(command=self.move_abs_v5)
        self.btn_motion["Stop"].configure(command=self.stop_path)
        self.btn_motion["resume"].configure(command=self.resume_v5)
        return self
    # ---------------- logic  ----------------
    def clamp(self, val, min_v, max_v):
        return max(min_v, min(val, max_v))

    def get_step(self):
        try:
            step = float(self.entry_settings["Step"].get())
            if step <= 0:
                raise ValueError
            return step
        except:
            step = 10.0
            self.entry_settings["Step"].delete(0, "end")
            self.entry_settings["Step"].insert(0, str(step))
            return step

    def jog(self, axis, direction):
        step = self.get_step()
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        current = self.state.pos[idx]
        target = current + step * direction
        target = self.clamp(target, 0, self.SLIDER_MAX[axis])
        delta = target - current

        self.log(
            f"JOG CMD axis={axis} step={step} dir={direction} "
            f"current={current:.3f} target={target:.3f} delta={delta:.3f}",
            "DEBUG"
        )

        if abs(delta) < 1e-6:
            self.log(f"JOG BLOCKED: {axis} limit reached", "WARN")
            return

        self.motion.jog(axis, delta)

    def commit_entry_xyz(self):
        try:
            x = float(self.entry_control["XC"].get())
            y = float(self.entry_control["YC"].get())
            z = float(self.entry_control["ZC"].get())

            if not (0 <= x <= self.SLIDER_MAX["X"]):
                self.log(f"XC OUT OF RANGE: {x} (allowed 0..{self.SLIDER_MAX['X']})", "WARN")
                self.entry_dirty["XC"] = False
                return False
            if not (0 <= y <= self.SLIDER_MAX["Y"]):
                self.log(f"YC OUT OF RANGE: {y} (allowed 0..{self.SLIDER_MAX['Y']})", "WARN")
                self.entry_dirty["YC"] = False
                return False
            if not (0 <= z <= self.SLIDER_MAX["Z"]):
                self.log(f"ZC OUT OF RANGE: {z} (allowed 0..{self.SLIDER_MAX['Z']})", "WARN")
                self.entry_dirty["ZC"] = False
                return False

            # sync sliders
            self.slider_pos["X"] = x
            self.slider_pos["Y"] = y
            self.slider_pos["Z"] = z
            self.slider_axis["X"].set(x)
            self.slider_axis["Y"].set(y)
            self.slider_axis["Z"].set(z)

            self.entry_dirty["XC"] = False
            self.entry_dirty["YC"] = False
            self.entry_dirty["ZC"] = False

            self.log(f"ENTRY ACCEPTED XC={x:.3f} YC={y:.3f} ZC={z:.3f}", "INPUT")
            return True

        except ValueError:
            self.log("INVALID INPUT: XC/YC/ZC must be numbers", "ERROR")
            return False

    def move_abs_v5(self):
        needs_commit = any(self.entry_dirty.get(k, False) for k in ("XC", "YC", "ZC"))
        if needs_commit:
            ok = self.commit_entry_xyz()
            if not ok:
                self.log("MOVE ABORTED: invalid target position", "WARN")
                return

        x = self.slider_pos["X"]
        y = self.slider_pos["Y"]
        z = self.slider_pos["Z"]

        self.log(f"MOVE CMD ABS x={x:.3f} y={y:.3f} z={z:.3f}", "CMD")
        self.motion.move_abs(x, y, z)

    def homing_v5(self):
        self.log("HOME CMD", "CMD")
        self.motion.home()

    def resume_v5(self):
        self.log("ACK/RESUME CMD", "CMD")
        self.motion.resume()

    def stop_path(self):
        self.log("STOP CMD", "CMD")
        self.path_engine.stop()
        self.motion.stop()

    # ---------------- entry bindings ----------------
    def _bind_entry_focus_and_dirty(self):
        def bind_focus(entry, key):
            entry.bind("<FocusIn>",  lambda e: self.entry_editing.__setitem__(key, True))
            entry.bind("<FocusOut>", lambda e: self.entry_editing.__setitem__(key, False))

        def bind_dirty(entry, key):
            def on_key(_):
                self.entry_dirty[key] = True
            entry.bind("<KeyRelease>", on_key)

        bind_focus(self.entry_control["XC"], "XC")
        bind_focus(self.entry_control["YC"], "YC")
        bind_focus(self.entry_control["ZC"], "ZC")

        bind_dirty(self.entry_control["XC"], "XC")
        bind_dirty(self.entry_control["YC"], "YC")
        bind_dirty(self.entry_control["ZC"], "ZC")

        # Enter commit 
        self.entry_control["XC"].bind("<Return>", lambda e: self.commit_entry_xyz())
        self.entry_control["YC"].bind("<Return>", lambda e: self.commit_entry_xyz())
        self.entry_control["ZC"].bind("<Return>", lambda e: self.commit_entry_xyz())
        self.entry_control["ZC"].bind("<Return>", lambda e: self.commit_entry_xyz())
