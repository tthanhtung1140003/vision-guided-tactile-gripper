import time
import cv2
import numpy as np
from picamera2 import Picamera2

from visionModule.config import *
from visionModule.detection import detect_dots, match_dots_knn, update_ref, draw_motion
from visionModule.slip_detection import slip_detector
from feature import display_params

from udp_receiver import UDPForceReceiver
force_receiver = UDPForceReceiver(port=5005)

picam2 = Picamera2(camera_num=0)
picam2.configure(picam2.create_video_configuration(main={"size": (3280, 2464)}))
picam2.set_controls({
    "AeEnable": False,
    "AwbEnable": False,
    "AnalogueGain": 2.0,
    "ExposureTime": 6000
})
picam2.start()
time.sleep(1)

frame = picam2.capture_array()
if frame is None:
    picam2.close()
    exit()

frame = cv2.resize(frame, FRAME_SIZE)

initial_dots = detect_dots(frame)
ref_dots = initial_dots.copy()
last_dxdy = np.zeros_like(ref_dots, dtype=np.float32)
motion_history = []
had_big_motion = False
prev_mean_disp = None

# ---- TRAIN DATA LOG ----
train_file = open("train_data_z.txt", "a")

while True:
    frame = picam2.capture_array()
    if frame is None:
        break

    frame = cv2.resize(frame, FRAME_SIZE)
    current_dots = detect_dots(frame)
    matches = match_dots_knn(ref_dots, current_dots, 10)

    motions, angles, displacements, vx_list, vy_list = [], [], [], [], []
    aligned = np.zeros_like(ref_dots, dtype=np.float32)

    for idx, ref_pt in enumerate(ref_dots):
        matched = [curr for r, curr in matches if (r == ref_pt).all()]
        if matched:
            x, y = matched[0]
            dx, dy = (x - ref_pt[0]), (y - ref_pt[1])
        else:
            dx, dy = last_dxdy[idx]
            x, y = ref_pt[0] + dx, ref_pt[1] + dy

        aligned[idx] = [x, y]
        prev_dx, prev_dy = last_dxdy[idx]
        vx = dx - prev_dx
        vy = dy - prev_dy
        vx_list.append(vx)
        vy_list.append(vy)
        motions.append(np.hypot(vx, vy))
        displacement_mag = np.hypot(dx, dy)
        displacements.append(displacement_mag)

        if displacement_mag < 1.4:
            angle = 0.0
        else:
            angle = np.degrees(np.arctan2(dy, dx))
        angles.append(angle)
        last_dxdy[idx] = np.array([dx, dy])

        draw_motion(frame, ref_pt, x, y, dx, dy)

    vx = np.array(vx_list)
    vy = np.array(vy_list)

    _, entropy = slip_detector(displacements, angles, motion_history, ref_dots, aligned)
    ref_dots, had_big_motion, last_dxdy = update_ref(last_dxdy, motions, displacements, aligned, ref_dots, had_big_motion)

    # ----- UDP -----
    fx, fy, fz = force_receiver.get_latest()
    if fz > 0 : fz=-fz

    cv2.putText(frame, f"Fx={fy:.2f} Fy={-fx:.2f} Fz={fz:.2f}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 1)

    # ----- LOG DATA 
    if abs(fz) > 0.1:
        feature_vec, label, prev_mean_disp = display_params(
            ref_dots,
            aligned,
            displacements,
            angles,
            entropy,
            vx,
            vy,
            fz,
            prev_mean_disp=prev_mean_disp,
            file=train_file
        )

    cv2.imshow("Camera 0", frame)
    if cv2.waitKey(30) & 0xFF == 27:
        break

train_file.close()
picam2.close()
cv2.destroyAllWindows()
