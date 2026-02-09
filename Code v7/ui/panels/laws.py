from ui.widgets.figma import create_button_group


class LawsPanel:
    def __init__(self, parent, *, on_gentleg=None, on_holding=None, on_adaption=None, on_handover=None):
        self.parent = parent

        self.on_gentleg = on_gentleg
        self.on_holding = on_holding
        self.on_adaption = on_adaption
        self.on_handover = on_handover

        self.btn_law = {}

        self.group_law = [
            ("Handover", 292, 349),
        ]
        self.handover_enabled = False
        self._handover_default_fg = None
        self._handover_default_hover = None
        self._handover_default_text = None

    def _toggle_handover(self):
        self.handover_enabled = not self.handover_enabled

        btn = self.btn_law.get("Handover")
        if not btn:
            return

        if self.handover_enabled:
            btn.configure(
                fg_color="#adc178",
                hover_color="#16a34a",
                text_color="white",
            )
        else:
            btn.configure(
                fg_color=self._handover_default_fg,
                hover_color=self._handover_default_hover,
                text_color=self._handover_default_text,
            )
        if self.on_handover:
            self.on_handover()

    def build(self):
        self.btn_law = create_button_group(self.parent, self.group_law, 120, 60)
        btn = self.btn_law.get("Handover")
        if btn is not None:
            self._handover_default_fg = btn.cget("fg_color")
            self._handover_default_hover = btn.cget("hover_color")
            self._handover_default_text = btn.cget("text_color")
            btn.configure(command=self._toggle_handover)

        return self
