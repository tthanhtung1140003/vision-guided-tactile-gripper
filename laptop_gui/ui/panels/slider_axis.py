from ui.widgets.figma import create_vertical_slider_group


class SliderAxisPanel:
    def __init__(self, parent, slider_pos, slider_max, on_change=None):
        self.parent = parent
        self.slider_pos = slider_pos
        self.slider_max = slider_max
        self.on_change = on_change  # optional callback: (axis, value) -> None

        self.slider_axis = {}

        self.group_slider_axis = [
            ("X",  48,  339, 370, "#4593AF"),
            ("Y",  123, 339, 370, "#E9C46A"),
            ("Z",  198, 339, 370, "#F4A261"),
        ]

    def build(self):
        self.slider_axis = create_vertical_slider_group(self.parent, self.group_slider_axis)

        self.slider_axis["X"].configure(
            from_=0,
            to=self.slider_max["X"],
            command=lambda v: self._on_slider("X", v),
        )
        self.slider_axis["Y"].configure(
            from_=0,
            to=self.slider_max["Y"],
            command=lambda v: self._on_slider("Y", v),
        )
        self.slider_axis["Z"].configure(
            from_=0,
            to=self.slider_max["Z"],
            command=lambda v: self._on_slider("Z", v),
        )

        # initial
        self.slider_axis["X"].set(self.slider_pos["X"])
        self.slider_axis["Y"].set(self.slider_pos["Y"])
        self.slider_axis["Z"].set(self.slider_pos["Z"])

        return self

    def _on_slider(self, axis, value):
        self.slider_pos[axis] = float(value)
        if self.on_change:
            self.on_change(axis, float(value))
