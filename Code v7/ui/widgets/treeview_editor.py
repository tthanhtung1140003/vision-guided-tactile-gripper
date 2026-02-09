import tkinter as tk
from tkinter import ttk


class TreeviewEditor:
    def __init__(self, tree: ttk.Treeview, get_data_cb, set_data_cb):
        self.tree = tree
        self.get_data = get_data_cb
        self.set_data = set_data_cb

        self._editing = False
        self._entry = None
        self._edit_ctx = None   # (idx, key)

        self.col_map = {
            "#2": "name",
            "#3": "x",
            "#4": "y",
            "#5": "z",
        }

        self.tree.bind("<Double-1>", self._on_double_click)

    # ================= DOUBLE CLICK =================

    def _on_double_click(self, event):
        if self._editing:
            return

        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)

        if not row or col not in self.col_map:
            return

        bbox = self.tree.bbox(row, col)
        if not bbox:
            return

        x, y, w, h = bbox
        item = self.tree.item(row)
        idx = int(item["values"][0])
        key = self.col_map[col]
        value = item["values"][int(col[1]) - 1]

        self._start_edit(x, y, w, h, idx, key, value)

    # ================= EDIT LIFECYCLE =================

    def _start_edit(self, x, y, w, h, idx, key, value):
        self._editing = True
        self._edit_ctx = (idx, key)

        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, value)
        entry.focus()
        entry.select_range(0, tk.END)

        entry.bind("<Return>", self._commit_event)
        entry.bind("<Escape>", self._cancel_event)
        entry.bind("<FocusOut>", self._focus_out_event)

        self._entry = entry

    # ================= EVENTS =================

    def _commit_event(self, event=None):
        self._commit()

    def _cancel_event(self, event=None):
        self._cleanup()

    def _focus_out_event(self, event=None):
        # click-outside auto commit
        if self._editing:
            self._commit()

    # ================= CORE =================

    def _commit(self):
        if not self._editing or not self._entry:
            return

        idx, key = self._edit_ctx
        try:
            val = self._entry.get()
            if key != "name":
                val = float(val)
            self.set_data(idx, key, val)
        except Exception as e:
            print("Treeview edit error:", e)
        finally:
            self._cleanup()

    def _cleanup(self):
        if self._entry:
            self._entry.destroy()

        self._entry = None
        self._edit_ctx = None
        self._editing = False
