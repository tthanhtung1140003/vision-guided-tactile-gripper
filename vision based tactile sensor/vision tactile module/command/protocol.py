#protocol.py

# ===== Laptop -> Pi =====
CMD_GRASPING_MODE = "Grasping_Mode"
CMD_APPROACH_DONE = "Approach_Done"
CMD_GRASPING_DONE = "Grasping_Mode_Done"

CMD_HOLD_MODE     = "Hold_Mode"
CMD_HANDOVER_MODE = "Handover_Mode"

CMD_TRACKING_MODE = "Tracking_Mode"
CMD_TRACKING_DONE   = "Tracking_Mode_Done"

CMD_STOP          = "STOP"

# ===== Pi -> Laptop =====
MSG_GRASP_DONE    = "Grasp_done"
MSG_HANDOVER_DONE = "Handover_done"
MSG_GRASP_FAIL    = "Grasp_fail"

MSG_MOVE_X_PLUS = "Move X+"
MSG_MOVE_Y_PLUS = "Move Y+"
MSG_MOVE_Z_PLUS = "Move Z+"

MSG_MOVE_X_MINUS = "Move X-"
MSG_MOVE_Y_MINUS = "Move Y-"
MSG_MOVE_Z_MINUS = "Move Z-"

MSG_STOP       = "STOP"

# ===== Gripper =====
GRIP_CLOSE   = "G"
GRIP_STOP    = "F"
GRIP_SQUEEZE = "S"
GRIP_LOOSEN  = "L"
GRIP_OPEN    = "R"