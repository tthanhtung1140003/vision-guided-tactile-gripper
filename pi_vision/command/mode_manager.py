# command/mode_manager.py
from command.protocol import *

class ModeManager:

    def __init__(self):
        self.mode = "IDLE"
        self.grasp_ready = False
        self.approach_ready = False

    # ==========================
    def handle_event(self, event: str):

        # ================= IDLE =================
        if self.mode == "IDLE":

            if event == CMD_GRASPING_MODE:
                self._transition("GRASPING")

            elif event == CMD_TRACKING_MODE:
                self._transition("TRACKING")

        # ================= GRASPING =================
        elif self.mode == "GRASPING":

            if event == "GRASP_FAIL":
                self.grasp_ready = False
                self.approach_ready = False
                self._transition("IDLE")

            elif event == "GRASP_DONE":
                self.grasp_ready = True

            elif event == CMD_APPROACH_DONE:
                self.approach_ready = True

            elif event == CMD_HOLD_MODE and self.grasp_ready:
                self._transition("HOLD")

            elif event == CMD_HANDOVER_MODE and self.grasp_ready:
                self._transition("HANDOVER")

        # ================= HOLD =================
        elif self.mode == "HOLD":

            if event == CMD_HANDOVER_MODE:
                self._transition("HANDOVER")

        # ================= HANDOVER =================
        elif self.mode == "HANDOVER":
            

            if event == "HANDOVER_DONE":
                self.grasp_ready = False
                self._transition("IDLE")

        # ================= TRACKING =================
        elif self.mode == "TRACKING":

            if event == CMD_TRACKING_DONE:
                self._transition("IDLE")

    # ==========================
    def _transition(self, new_mode: str):
        print(f"🔁 {self.mode} → {new_mode}")

        self.mode = new_mode

        if new_mode == "GRASPING":
            self.approach_ready = False
            self.grasp_ready = False
