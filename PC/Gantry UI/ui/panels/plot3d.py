from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui.widgets.figma import create_vertical_slider_group, create_label_group

class Plot3DPanel:
    def __init__(self, parent, root, x=430, y=320, w=400, h=400):
        self.parent = parent
        self.root = root
        self.x = x
        self.y = y
        self.w = w
        self.h = h

        self.fig = None
        self.ax = None
        self.canvas = None

    def build(self):
        # ===== MATPLOT FUNCTION =====
        self.fig = Figure(figsize=(2, 1.5), dpi=100)
        self.ax = self.fig.add_subplot(111, projection="3d")

        # default setup (giữ giống bản gốc)
        self.ax.set_xlim(-1, 1)
        self.ax.set_ylim(-1, 1)
        self.ax.set_zlim(0, 1)
        self.ax.set_box_aspect([1, 1, 1])
        self.ax.set_proj_type("ortho")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.draw()

        self.canvas.get_tk_widget().place(
            x=self.x, y=self.y, width=self.w, height=self.h
        )

        # khóa tương tác (giữ y hệt)
        for event in (
            "button_press_event",
            "button_release_event",
            "motion_notify_event",
            "scroll_event",
            "key_press_event",
        ):
            self.canvas.mpl_connect(event, lambda e: None)

        return self

    def update(self, state, slider_pos, slider_view, slider_max):
        ax = self.ax
        canvas = self.canvas
        if ax is None or canvas is None:
            return

        ax.cla()

        elev = slider_view["vertical"].get()
        azim = slider_view["horizontal"].get()
        ax.view_init(elev=elev, azim=azim)

        ax.set_xlim(0, slider_max["X"])
        ax.set_ylim(0, slider_max["Y"])
        ax.set_zlim(slider_max["Z"], 0)
        ax.set_box_aspect([1, 1, 1])
        ax.set_proj_type("ortho")

        # path points
        if state.points:
            xs = [p["x"] for p in state.points]
            ys = [p["y"] for p in state.points]
            zs = [p["z"] for p in state.points]

            ax.plot(xs, ys, zs, marker="o", color="gray")

            if state.active_point_index >= 0:
                i = state.active_point_index
                ax.scatter(xs[i], ys[i], zs[i], color="red", s=80)

        # slider point (relative)
        ax.scatter(
            slider_pos["X"],
            slider_pos["Y"],
            slider_pos["Z"],
            color="blue",
            s=60,
        )

        # current position (absolute)
        ax.scatter(
            state.pos[0],
            state.pos[1],
            state.pos[2],
            color="green",
            s=40,
        )

        # axes cosmetics (giữ y hệt)
        ax.xaxis.line.set_color("#4593AF")
        ax.yaxis.line.set_color("#E9C46A")
        ax.zaxis.line.set_color("#F4A261")
        ax.tick_params(axis="x", colors="#4593AF")
        ax.tick_params(axis="y", colors="#E9C46A")
        ax.tick_params(axis="z", colors="#F4A261")

        canvas.draw_idle()


class PlotControlsPanel:
    """
    Controls cho plot:
    - slider_view: vertical/horizontal (coords giữ nguyên)
    - labels_plot: Xs/Ys/Zs (coords giữ nguyên)
    """

    def __init__(self, parent, slider_pos):
        self.parent = parent
        self.slider_pos = slider_pos

        self.slider_view = {}
        self.labels_plot = {}

        self.group_slider_direction = [
            ("vertical",   840, 349, 150, "#a1e887"),
            ("horizontal", 840, 559, 150, "#a1e887"),
        ]
        self.group_labels_plot = [
            ("Xs", 180, 232, 80, 30, 20, "0.00"),
            ("Ys", 180, 268, 80, 30, 20, "0.00"),
            ("Zs", 180, 304, 80, 30, 20, "0.00"),
        ]

    def build(self):
        self.slider_view = create_vertical_slider_group(self.parent, self.group_slider_direction)
        self.slider_view["vertical"].configure(from_=-90, to=90)
        self.slider_view["horizontal"].configure(from_=-180, to=180)
        self.slider_view["vertical"].set(30)
        self.slider_view["horizontal"].set(45)

        self.labels_plot = create_label_group(self.parent, self.group_labels_plot)
        return self

    def tick(self):
        self.labels_plot["Xs"].configure(text=f"{self.slider_pos['X']:.2f}")
        self.labels_plot["Ys"].configure(text=f"{self.slider_pos['Y']:.2f}")
        self.labels_plot["Zs"].configure(text=f"{self.slider_pos['Z']:.2f}")