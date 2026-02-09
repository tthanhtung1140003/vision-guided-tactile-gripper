import customtkinter as ctk
import sys
from core.state import SystemState
from core.serial_manager import SerialManager
from core.motion_controller import MotionController
from core.path_engine import PathEngine
from ui.app_ui import AppUI

LIMIT_EPS = 0.01
_last_limit_state = {"X": None, "Y": None, "Z": None}
entry_editing = {"XC": False, "YC": False, "ZC": False}
entry_dirty = {"XC": False, "YC": False, "ZC": False}
slider_pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
SLIDER_MAX = {"X": 300, "Y": 300, "Z": 200}

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("Control")
root.geometry("1366x768")
root.state("zoomed")

state = SystemState()
serial_mgr = SerialManager(state)
motion = MotionController(state, serial_mgr)
path_engine = PathEngine(state, motion)

ui = AppUI(
    root, state, serial_mgr, motion, path_engine,
    slider_pos=slider_pos,
    slider_max=SLIDER_MAX,
    entry_editing=entry_editing,
    entry_dirty=entry_dirty,
    limit_eps=LIMIT_EPS,
    last_limit_state=_last_limit_state,
)

def on_close():
    try:
        path_engine.stop()
    except Exception:
        pass
    try:
        serial_mgr.send("STOP")
    except Exception:
        pass
    try:
        serial_mgr.disconnect(reason="APP_CLOSE")
    except Exception:
        pass
    root.destroy()
    sys.exit(0)

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
