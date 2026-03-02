import customtkinter as ctk
import tkinter as tk


class LogPanel:
    def __init__(self, parent, x=294, y=200, width=590, height=88):
        self.parent = parent
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        self.frame = None
        self.text = None
        self.scroll = None

    def build(self):
        # ===== LOG TABLE =====
        self.frame = ctk.CTkFrame(
            self.parent,
            width=self.width,
            height=self.height,
            fg_color="#EEEEEE",
            corner_radius=8,
            border_width=0,
        )
        self.frame.place(x=self.x, y=self.y)

        self.frame.grid_propagate(False)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

        self.text = tk.Text(
            self.frame,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#EEEEEE",
            fg="#000000",
            relief="flat",
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=8)
        self.text.config(state="disabled")

        self.scroll = tk.Scrollbar(
            self.frame,
            orient="vertical",
            command=self.text.yview,
        )
        self.scroll.grid(row=0, column=1, sticky="ns", pady=8)

        self.text.config(yscrollcommand=self.scroll.set)

        return self

    def append_line(self, line: str):
        if not self.text:
            return
        self.text.config(state="normal")
        self.text.insert("end", line)
        self.text.see("end")  # auto scroll
        self.text.config(state="disabled")

    def append(self, msg: str, tag: str = "INFO", timestamp: str = ""):
        if timestamp:
            line = f"[{timestamp}] [{tag}] {msg}\n"
        else:
            line = f"[{tag}] {msg}\n"
        self.append_line(line)
