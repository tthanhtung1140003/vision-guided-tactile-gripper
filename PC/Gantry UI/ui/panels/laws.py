from ui.widgets.figma import create_button_group


class LawsPanel:
    """4 buttons as the "test 4 nút" spec (PC GUI ↔ Pi protocol).

    Buttons:
      - Grasping_Mode
      - Approach_Done
      - Handover_Mode
      - Tracking_Mode

    The panel is intentionally dumb: it only triggers callbacks and exposes helpers
    to enable/disable and highlight active state.
    """

    def __init__(
        self,
        parent,
        *,
        on_grasping_mode=None,
        on_approach_done=None,
        on_handover_mode=None,
        on_tracking_toggle=None,
    ):
        self.parent = parent
        self.on_grasping_mode = on_grasping_mode
        self.on_approach_done = on_approach_done
        self.on_handover_mode = on_handover_mode
        self.on_tracking_toggle = on_tracking_toggle

        self.btn_law = {}
        self.group_law = [
            ("Grasping_Mode", 292, 339),
            ("Approach_Done", 292, 384),
            ("Handover_Mode", 292, 429),
            ("Tracking_Mode", 292, 484),
        ]

        self._defaults = {}  # name -> (fg, hover, text)
        self._active_name = None
        self._commands = {}  # name -> callable (restored when enabled)

    @staticmethod
    def _noop(*_args, **_kwargs):
        """Used to guarantee a button does nothing when disabled."""
        return

    def _set_cursor_like(self, btn, cursor: str):
        """Force cursor on CTkButton and its internal widgets (avoid stale hand cursor)."""
        try:
            btn.configure(cursor=cursor)
        except Exception:
            pass
        # CustomTkinter internal widgets (best-effort; attribute names may differ by version)
        for attr in ("_canvas", "_text_label", "_image_label"):
            try:
                w = getattr(btn, attr, None)
                if w is not None:
                    w.configure(cursor=cursor)
            except Exception:
                pass

    def build(self):
        self.btn_law = create_button_group(self.parent, self.group_law, 120, 35)

        # Display labels (user-facing) — keep internal keys for protocol compatibility.
        labels = {
            "Grasping_Mode": "Grasping",
            "Approach_Done": "Approach",
            "Handover_Mode": "Handover",
            "Tracking_Mode": "Tracking",
        }
        for key, label in labels.items():
            try:
                if self.btn_law.get(key):
                    self.btn_law[key].configure(text=label)
            except Exception:
                pass

        for name in ("Grasping_Mode", "Approach_Done", "Handover_Mode", "Tracking_Mode"):
            if self.btn_law.get(name):
                self._store_defaults(name)

        # Wire commands and remember them so we can truly disable by swapping command -> noop.
        if self.btn_law.get("Grasping_Mode"):
            self._commands["Grasping_Mode"] = self._on_grasping_clicked
            self.btn_law["Grasping_Mode"].configure(command=self._on_grasping_clicked)
        if self.btn_law.get("Approach_Done"):
            self._commands["Approach_Done"] = self._on_approach_clicked
            self.btn_law["Approach_Done"].configure(command=self._on_approach_clicked)
        if self.btn_law.get("Handover_Mode"):
            self._commands["Handover_Mode"] = self._on_handover_clicked
            self.btn_law["Handover_Mode"].configure(command=self._on_handover_clicked)
        if self.btn_law.get("Tracking_Mode"):
            self._commands["Tracking_Mode"] = self._on_tracking_clicked
            self.btn_law["Tracking_Mode"].configure(command=self._on_tracking_clicked)

        return self

    def _store_defaults(self, name: str):
        btn = self.btn_law.get(name)
        if not btn:
            return
        # do not highlight a disabled button
        try:
            if str(btn.cget("state")) == "disabled":
                return
        except Exception:
            pass
        self._defaults[name] = (btn.cget("fg_color"), btn.cget("hover_color"), btn.cget("text_color"))

    
    def _is_enabled(self, name: str) -> bool:
        btn = self.btn_law.get(name)
        if not btn:
            return False
        try:
            return str(btn.cget("state")) != "disabled"
        except Exception:
            return True

    def _set_btn_state(self, name: str, enabled: bool):
        btn = self.btn_law.get(name)
        if not btn:
            return

        if enabled:
            # enable thật
            btn.configure(state="normal", hover=True)
            # enabled cursor can be hand; disabled must stay arrow like Resume
            self._set_cursor_like(btn, "hand2")
            # restore command (important: guarantees disabled really blocks clicks)
            if name in self._commands:
                btn.configure(command=self._commands[name])
            # restore default colors unless this button is currently active-highlighted
            if name in self._defaults and self._active_name != name:
                fg, hover, text = self._defaults[name]
                btn.configure(fg_color=fg, hover_color=hover, text_color=text)
        else:
            # disable thật (giống Resume): no hover, arrow cursor everywhere
            btn.configure(state="disabled", hover=False)
            self._set_cursor_like(btn, "arrow")
            # swap command to noop to guarantee no action even if CTk still triggers command
            btn.configure(command=self._noop)
            # muted disabled look
            btn.configure(
                fg_color="#F2F3F5",
                hover_color="#F2F3F5",
                text_color="#9AA0A6",
            )

    def set_enabled(self, *, grasping=None, approach=None, handover=None, tracking=None):
        if grasping is not None:
            self._set_btn_state("Grasping_Mode", bool(grasping))
        if approach is not None:
            self._set_btn_state("Approach_Done", bool(approach))
        if handover is not None:
            self._set_btn_state("Handover_Mode", bool(handover))
        if tracking is not None:
            self._set_btn_state("Tracking_Mode", bool(tracking))

    def set_tracking_active(self, active: bool):
        """Tracking button should keep a single visual state (no Tracking/Stop toggle)."""
        btn = self.btn_law.get("Tracking_Mode")
        if not btn:
            return
        # Always keep the same label and colors; running/stopped is handled by logic, not visuals.
        btn.configure(text="Tracking")

    def set_active(self, name: str | None):
        # restore previous
        if self._active_name and self._active_name in self._defaults:
            fg, hover, text = self._defaults[self._active_name]
            btn = self.btn_law.get(self._active_name)
            if btn:
                btn.configure(fg_color=fg, hover_color=hover, text_color=text)

        self._active_name = None
        if not name:
            return

        btn = self.btn_law.get(name)
        if not btn:
            return
        # do not highlight a disabled button
        try:
            if str(btn.cget("state")) == "disabled":
                return
        except Exception:
            pass

        self._active_name = name
        # active highlight
        btn.configure(fg_color="#adc178", hover_color="#16a34a", text_color="white")

    # callbacks
    def _on_grasping_clicked(self):
        if not self._is_enabled("Grasping_Mode"):
            return
        if self.on_grasping_mode:
            self.on_grasping_mode()

    def _on_approach_clicked(self):
        if not self._is_enabled("Approach_Done"):
            return
        if self.on_approach_done:
            self.on_approach_done()

    def _on_handover_clicked(self):
        if not self._is_enabled("Handover_Mode"):
            return
        if self.on_handover_mode:
            self.on_handover_mode()

    def _on_tracking_clicked(self):
        if not self._is_enabled("Tracking_Mode"):
            return
        if self.on_tracking_toggle:
            self.on_tracking_toggle()
