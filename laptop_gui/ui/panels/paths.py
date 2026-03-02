import os
import json
from tkinter import ttk

from ui.widgets.figma import (
    create_button_group,
    create_entry_group,
    create_combobox_group,
)
from ui.widgets.treeview_editor import TreeviewEditor

class PathPanel:
    def __init__(self, parent, state, path_engine, motion, log_cb):
        self.parent = parent
        self.state = state
        self.path_engine = path_engine
        self.motion = motion
        self.log = log_cb
        # widgets (expose)
        self.tree_points = None
        self.tree_editor = None
        self.combo_save = {}
        self.entry_save = {}
        self.btn_program = {}

        self.on_point_selected = None
        # groups 
        self.group_program = [
            ("Save",   1135, 643),
            ("Load",   1240, 643),
            ("Add",     925, 689),
            ("Run",    1030, 689),
            ("Delete", 1135, 689),
            ("Clear",  1240, 689),
        ]
        self.group_entries_save = [
            ("save", 1030, 643, 95, 30, "Save"),
        ]
        self.group_combo_save = [
            ("path_name", 925, 643, 95, 30, [], "None"),
        ]

        self._setup_tree_style_done = False

    # ---------------- build ----------------
    def build(self):
        self._setup_tree_style()

        # Treeview
        columns = ("label", "name", "x", "y", "z")
        self.tree_points = ttk.Treeview(
            self.parent,
            columns=columns,
            show="headings",
            style="Points.Treeview",
            selectmode="browse",
            height=5,
        )
        self.tree_points.heading("label", text="#")
        self.tree_points.heading("name",  text="Name")
        self.tree_points.heading("x",     text="X")
        self.tree_points.heading("y",     text="Y")
        self.tree_points.heading("z",     text="Z")

        self.tree_points.column("label", width=30, anchor="center")
        self.tree_points.column("name",  width=80, anchor="w")
        self.tree_points.column("x",     width=60, anchor="e")
        self.tree_points.column("y",     width=60, anchor="e")
        self.tree_points.column("z",     width=60, anchor="e")

        self.tree_points.place(x=925, y=461, width=410, height=150)
        # Tree editor (double-click edit)
        self.tree_editor = TreeviewEditor(
            self.tree_points,
            self.get_point,
            self.set_point,
        )
        self.tree_points.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.entry_save = create_entry_group(self.parent, self.group_entries_save)
        self.combo_save = create_combobox_group(self.parent, self.group_combo_save)
        self.combo_save["path_name"].configure(values=["None"])
        self.combo_save["path_name"].set("None")

        self.btn_program = create_button_group(self.parent, self.group_program, 95, 30)
        self.btn_program["Save"].configure(command=self.save_path)

        self.btn_program["Load"].configure(command=self.load_button_handler)

        self.btn_program["Run"].configure(command=self.run_path)

        self.btn_program["Add"].configure(command=self.add_point_from_current)
        self.btn_program["Delete"].configure(command=self.delete_selected_point)
        self.btn_program["Clear"].configure(command=self.clear_all_points)

        self.refresh_path_list()

        self.refresh_point_tree()

        return self

    # ---------------- style ----------------
    def _setup_tree_style(self):
        if self._setup_tree_style_done:
            return
        style = ttk.Style()
        style.configure(
            "Points.Treeview",
            background="#EEEEEE",
            fieldbackground="#EEEEEE",
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Points.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
        )
        self._setup_tree_style_done = True

    # ---------------- helpers ----------------
    def index_to_name(self, i):
        return chr(ord("A") + i)

    def normalize_point_names(self):
        for i, p in enumerate(self.state.points):
            p["name"] = chr(ord("A") + i)

    def get_point(self, idx):
        return self.state.points[idx]

    def set_point(self, idx, key, value):
        self.state.points[idx][key] = value
        self.normalize_point_names()
        self.refresh_point_tree()

    # ---------------- tree ops ----------------
    def refresh_point_tree(self):
        if not self.tree_points:
            return
        self.tree_points.delete(*self.tree_points.get_children())
        for i, p in enumerate(self.state.points):
            tags = ("active",) if i == self.state.active_point_index else ()
            self.tree_points.insert(
                "",
                "end",
                values=(
                    i,
                    p.get("name", self.index_to_name(i)),
                    f"{p.get('x', 0.0):.3f}",
                    f"{p.get('y', 0.0):.3f}",
                    f"{p.get('z', 0.0):.3f}",
                ),
                tags=tags,
            )
        self.tree_points.tag_configure("active", background="#FFD966")

    def on_tree_select(self, _event=None):
        sel = self.tree_points.selection()
        if not sel:
            return
        idx = int(self.tree_points.item(sel[0], "values")[0])
        self.state.active_point_index = idx

        if self.on_point_selected and 0 <= idx < len(self.state.points):
            self.on_point_selected(idx, self.state.points[idx])
    # ---------------- point commands ----------------
    def add_point_from_current(self):
        i = len(self.state.points)
        p = {
            "name": self.index_to_name(i),
            "x": float(getattr(self, "slider_pos", {}).get("X", 0.0)) if hasattr(self, "slider_pos") else 0.0,
            "y": float(getattr(self, "slider_pos", {}).get("Y", 0.0)) if hasattr(self, "slider_pos") else 0.0,
            "z": float(getattr(self, "slider_pos", {}).get("Z", 0.0)) if hasattr(self, "slider_pos") else 0.0,
        }
        # Nếu bạn muốn add theo slider_pos của GUI, hãy set panel.slider_pos từ ngoài (xem 6.2)
        self.state.points.append(p)
        self.refresh_point_tree()

    def delete_selected_point(self):
        sel = self.tree_points.selection()
        if not sel:
            return
        idx = int(self.tree_points.item(sel[0], "values")[0])
        if 0 <= idx < len(self.state.points):
            self.state.points.pop(idx)
        self.normalize_point_names()
        self.refresh_point_tree()

    def clear_all_points(self):
        self.state.points.clear()
        self.state.active_point_index = -1
        self.refresh_point_tree()

    # ---------------- run/stop ----------------
    def run_path(self):
        if not self.state.points:
            self.log("No points to run", "WARN")
            return
        start_idx = getattr(self.state, "active_point_index", -1)
        if start_idx is None or start_idx < 0 or start_idx >= len(self.state.points):
            start_idx = 0
        self.log(f"Run path from point #{start_idx}", "INFO")
        self.path_engine.start(start_index=start_idx)

    def stop_path(self):
        self.path_engine.stop()
        self.motion.stop()

    # ---------------- save/load paths ----------------
    def save_path(self):
        name = self.entry_save["save"].get().strip()
        if not name:
            self.log("Save name empty", "WARN")
            return
        os.makedirs("paths", exist_ok=True)
        path = f"paths/{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.state.points, f, indent=2)
        self.log(f"Saved path: {name}", "INFO")
        self.refresh_path_list()

    def load_path(self):
        name = self.combo_save["path_name"].get()
        if not name or name == "None":
            self.log("No path selected", "WARN")
            return
        path = f"paths/{name}.json"
        if not os.path.exists(path):
            self.log(f"Path not found: {name}", "ERROR")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.state.points = json.load(f)
            self.normalize_point_names()
            self.state.active_point_index = -1
            self.refresh_point_tree()
            self.log(f"Loaded path: {name}", "INFO")
        except Exception as e:
            self.log(f"Load failed: {e}", "ERROR")

    def scan_paths_only(self):
        os.makedirs("paths", exist_ok=True)
        names = [
            os.path.splitext(f)[0]
            for f in os.listdir("paths")
            if f.endswith(".json")
        ]
        if not names:
            self.combo_save["path_name"].configure(values=["None"])
            self.combo_save["path_name"].set("None")
            self.log("No paths found", "INFO")
        else:
            self.combo_save["path_name"].configure(values=names)
            self.combo_save["path_name"].set(names[0])
            self.log(f"Found {len(names)} path(s)", "INFO")

    def load_button_handler(self):
        current = self.combo_save["path_name"].get()
        if current == "None":
            self.scan_paths_only()
            return
        self.load_path()

    def refresh_path_list(self):
        os.makedirs("paths", exist_ok=True)
        names = [
            os.path.splitext(f)[0]
            for f in os.listdir("paths")
            if f.endswith(".json")
        ]
        if not names:
            self.combo_save["path_name"].configure(values=["None"])
            self.combo_save["path_name"].set("None")
        else:
            self.combo_save["path_name"].configure(values=names)
            self.combo_save["path_name"].set(names[0])
