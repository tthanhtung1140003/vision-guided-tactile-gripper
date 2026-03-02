#command/command_router.py
from command.protocol import *
from command.mode_manager import ModeManager

class CommandRouter:

    def __init__(self, gripper, laptop):
        self.gripper = gripper
        self.laptop  = laptop
        self.mode_mgr = ModeManager()

        self.prev_mode = self.mode_mgr.mode
        self.handover_triggered = False
        self.grasp_completed = False
        self.extra_squeezed = False

        self.hold_current_angle = 0
        self.hold_cooldown = 0

        self.last_tracking_cmd = None
        self.tracking_cooldown = 0

    def update(self, 
                slip_score=None, 
                contact_state0=None, contact_state1=None, 
                tar_value=None,
                meanx0=None, meany0=None, mean0=None,
                meanx1=None, meany1=None, mean1=None):
        # Nhận lệnh từ Laptop
        cmd = self.laptop.read()
        if cmd:
            self.mode_mgr.handle_event(cmd)

        # Nhận trạng thái từ STM32 (gripper)
        g_state = self.gripper.read_state()
        if g_state:
            self._handle_gripper_state(g_state)

        # Phát hiện mode chuyển đổi
        current_mode = self.mode_mgr.mode

        if current_mode != self.prev_mode:

            print(f"[MODE] {self.prev_mode} -> {current_mode}")

            # Reset handover trigger khi vào HANDOVER
            if current_mode == "HANDOVER":
                self.handover_triggered = False
            if current_mode == "GRASPING":
                self.grasp_completed = False
                self.extra_squeezed = False   

            self.prev_mode = current_mode

        # Chạy logic logic
        if current_mode == "GRASPING":
             # ----- Grip fail check -----
            FAIL_THRESHOLD = 720

            if tar_value is not None and tar_value > FAIL_THRESHOLD:
                self.gripper.stop()
                self.gripper.open()   
                self.mode_mgr.handle_event("GRASP_FAIL")
                self.laptop.send(MSG_GRASP_FAIL)

                return

            # ----- Normal grasp -----
            if self.mode_mgr.approach_ready:
                self._grasping_logic(slip_score, contact_state0, contact_state1)

        elif current_mode == "HOLD":
            self._hold_logic(slip_score)

        elif current_mode == "HANDOVER":
            self._handover_logic(slip_score)

        elif current_mode == "TRACKING":
            if self.tracking_cooldown > 0:
                self.tracking_cooldown -= 1

            self._tracking_logic(meanx0, meany0, mean0,
                                meanx1, meany1, mean1,
                                contact_state0, contact_state1)


    # ==================================================
    def _grasping_logic(self, slip, contact_state0, contact_state1):

        if self.grasp_completed:
            return

        if contact_state0 is None or contact_state1 is None:
            return

        # Chưa chạm vật → tiếp tục đóng
        if contact_state0 == 0 and contact_state1 == 0:
            self.gripper.squeeze(7)

        # Chạm 1 bên → tiếp tục đóng nhẹ
        elif (contact_state0 == 1 and contact_state1 == 0) or ( contact_state0 == 0 and contact_state1 == 1):
            self.gripper.squeeze(3)

        # Đã chạm vật
        elif contact_state0 == 1 and contact_state1 == 1:
            # Stop đóng chính
            self.gripper.stop()

            # squeeze thêm đúng 1 lần
            if not self.extra_squeezed:
                print("[GRASP] Contact detected → micro squeeze 5°")
                self.gripper.squeeze(2)
                self.extra_squeezed = True

            # Hoàn thành
            self.grasp_completed = True

            self.mode_mgr.handle_event("GRASP_DONE")
            self.laptop.send(MSG_GRASP_DONE)

            print("[GRASP] Done")

    # ==================================================
    def _hold_logic(self, slip):

        if slip is None:
            return

        if self.hold_cooldown > 0:
            self.hold_cooldown -= 1

        MIN_SLIP = 0.5
        MAX_SLIP = 1.0

        MIN_ANGLE = 2
        MAX_ANGLE = 7

        # =========================
        # SLIP ACTIVE ZONE
        # =========================
        if slip > MIN_SLIP:

            # Clamp slip
            slip_clamped = min(max(slip, MIN_SLIP), MAX_SLIP)

            # Normalize 0→1
            alpha = (slip_clamped - MIN_SLIP) / (MAX_SLIP - MIN_SLIP)

            # Target angle
            target_angle = MIN_ANGLE + alpha * (MAX_ANGLE - MIN_ANGLE)
            target_angle = int(round(target_angle))

            delta = target_angle - self.hold_current_angle

            # Chỉ điều chỉnh khi chênh lệch đủ lớn
            if abs(delta) >= 1 and self.hold_cooldown == 0:

                if delta > 0:
                    print(f"[HOLD] Increase grip {delta}°")
                    self.gripper.squeeze(delta)
                else:
                    print(f"[HOLD] Decrease grip {-delta}°")
                    self.gripper.loosen(-delta)

                self.hold_current_angle = target_angle
                self.hold_cooldown = 3

        # =========================
        # NO SLIP
        # =========================
        else:

            if self.hold_current_angle > 0 and self.hold_cooldown == 0:

                print("[HOLD] Slip gone → release extra grip")

                self.gripper.loosen(self.hold_current_angle)

                self.hold_current_angle = 0
                self.hold_cooldown = 5

    # ==================================================
    def _handover_logic(self, slip):
        if slip is None:
            return

        THRESHOLD = 0.6

        if slip > THRESHOLD and not self.handover_triggered:
            print("[HANDOVER] Release triggered")
            self.gripper.open()
            self.handover_triggered = True
            self.laptop.send(MSG_HANDOVER_DONE)

    # ==================================================
    def _tracking_logic(self,
                        meanx0, meany0, mean0,
                        meanx1, meany1, mean1,
                        contact_state0, contact_state1):

        cmd_to_send = None

        # ================= SAFETY CHECK =================
        if contact_state0 is None or contact_state1 is None:
            if self.last_tracking_cmd is not None:
                print("[TRACKING] Send STOP")
                self.laptop.send(MSG_STOP)
                self.last_tracking_cmd = None
                self.tracking_cooldown = 3
            return

        # ================= CAM 0 =========================
        if contact_state0 == 1 and contact_state1 == 0:

            if None not in (meanx0, meany0, mean0):

                ratio0 = meanx0 / (meany0 + 1e-6)

                if meanx0 > 2 * meany0:
                    cmd_to_send = MSG_MOVE_X_PLUS

                elif meany0 > 2 * meanx0:
                    cmd_to_send = MSG_MOVE_Y_PLUS

                elif mean0 > 6.0 and 1 <= ratio0 <= 2:
                    cmd_to_send = MSG_MOVE_Z_PLUS

        # ================= CAM 1 =========================
        elif contact_state1 == 1 and contact_state0 == 0:

            if None not in (meanx1, meany1, mean1):

                ratio1 = meanx1 / (meany1 + 1e-6)

                if meanx1 > 2 * meany1:
                    cmd_to_send = MSG_MOVE_X_MINUS

                elif meany1 > 2 * meanx1:
                    cmd_to_send = MSG_MOVE_Y_MINUS

                elif mean1 > 6.0 and 1 <= ratio1 <= 2:
                    cmd_to_send = MSG_MOVE_Z_MINUS

        # =================================================
        # ============== NO CONDITION MATCH ===============
        # =================================================
        if cmd_to_send is None:
            if self.last_tracking_cmd is not None:
                print("[TRACKING] Send STOP")
                self.laptop.send(MSG_STOP)
                self.last_tracking_cmd = None
                self.tracking_cooldown = 3
            return

        # =================================================
        # ============== COOLDOWN =========================
        # =================================================
        if self.tracking_cooldown > 0:
            self.tracking_cooldown -= 1
            return

        # =================================================
        # ============== SEND COMMAND =====================
        # =================================================
        if cmd_to_send != self.last_tracking_cmd:

            print(f"[TRACKING] Send {cmd_to_send}")
            self.laptop.send(cmd_to_send)

            self.last_tracking_cmd = cmd_to_send
            self.tracking_cooldown = 5