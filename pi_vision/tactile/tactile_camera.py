import cv2
import numpy as np
import time
from picamera2 import Picamera2

from tactile.config_override import get_config, cam1_edit
from tactile.detection import (
    detect_dots, match_dots_knn,
    update_ref, draw_motion, compute_dot_count
)
from tactile.slip_detector_quantitative import slip_detector_quantitative1
from tactile.feature_bulder import build_feature_vector
from tactile.force_infer import predict_force

def tactile_cam_loop(cam_id: int, show=True):
    cfg = get_config(cam_id)

    # ================= CAMERA =================
    picam2 = Picamera2(camera_num=cam_id)

    full_res = (3280, 2464)
    video_config = picam2.create_video_configuration(
        main={"size": full_res}
    )
    picam2.configure(video_config)

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
        print(f"Không đọc được camera {cam_id}")
        picam2.close()
        return

    frame = cv2.resize(frame, cfg.FRAME_SIZE)
    if cam_id == 1:
        frame = cam1_edit(frame,0.926,30,20)

    # ================= INIT =================
    initial_dots = detect_dots(frame, cfg)
    ref_dots = initial_dots.copy()

    last_dxdy = np.zeros_like(ref_dots, dtype=np.float32)
    motion_history = []
    had_big_motion = False
    prev_mean_disp = 0.0

    initial_cell_areas = None
    initial_cell_centers = None

    # ================= MAIN LOOP =================
    try:
        while True:
            frame = picam2.capture_array()
            if frame is None:
                break

            frame = cv2.resize(frame, cfg.FRAME_SIZE)
            if cam_id == 1:
                frame = cam1_edit(frame,0.926,30,20)

            current_dots = detect_dots(frame, cfg)
            matches = match_dots_knn(ref_dots, current_dots, 10)

            motions = []
            angles = []
            displacements = []
            dx_list, dy_list = [], []
            vx_list, vy_list = [], []

            aligned = np.zeros_like(ref_dots, dtype=np.float32)

            # ---------- Motion extraction ----------
            for idx, ref_pt in enumerate(ref_dots):
                matched = [c for r, c in matches if (r == ref_pt).all()]
                if matched:
                    x, y = matched[0]
                    dx = ((x - ref_pt[0]) * 10) // 1 / 10
                    dy = ((y - ref_pt[1]) * 10) // 1 / 10
                else:
                    dx, dy = last_dxdy[idx]
                    x, y = ref_pt[0] + dx, ref_pt[1] + dy

                dx_list.append(dx)
                dy_list.append(dy)
                aligned[idx] = [x, y]

                prev_dx, prev_dy = last_dxdy[idx]
                vx = dx - prev_dx
                vy = dy - prev_dy

                vx_list.append(vx)
                vy_list.append(vy)

                motion = np.hypot(vx, vy)
                disp = np.hypot(dx, dy)

                motions.append(motion)
                displacements.append(disp)
                max_disp = np.max(displacements)

                angle = 0.0 if disp < 1.4 else np.degrees(np.arctan2(dy, dx))
                angles.append(angle)

                last_dxdy[idx] = [dx, dy]

                draw_motion(frame, ref_pt, x, y, dx, dy, cfg)

            if len(aligned) != 25:
                continue

            grid = aligned.reshape(5, 5, 2)

            mean_dx = float(np.mean(dx_list)) if dx_list else 0.0
            mean_dy = float(np.mean(dy_list)) if dy_list else 0.0

            # ================= DOT COUNT =================
            dot_count, initial_cell_areas, initial_cell_centers, black_window = compute_dot_count(
                grid,
                initial_cell_areas,
                initial_cell_centers
            )

            if dot_count == 0:
                contact_state = 0
            elif dot_count >=1 :
                contact_state = 1

            # ---------- Slip detection ----------
            metrics = slip_detector_quantitative1(
                displacements=displacements,
                angles=angles,
                motion_history=motion_history,
                ref_points=ref_dots,
                new_points=aligned,
                cfg=cfg
            )

            # ---------- Update reference ----------
            ref_dots, had_big_motion, last_dxdy = update_ref(
                last_dxdy,
                motions,
                displacements,
                aligned,
                ref_dots,
                had_big_motion,
                cfg=cfg
            )

            # ---------- Force ML ----------
            feature_vec, mean_disp = build_feature_vector(
                ref_dots,
                aligned,
                displacements,
                angles,
                metrics["entropy"],
                vx,
                vy,
                prev_mean_disp
            )
            prev_mean_disp = mean_disp

            fx_ml, fy_ml, fz_ml = predict_force(feature_vec, cam_id)
            fx_ml, fy_ml, fz_ml = map(lambda x: round(x, 1), (fx_ml, fy_ml, fz_ml))

            # ---------- OUTPUT STATE ----------
            camera_state = {
                "cam_id": cam_id,

                "slip_score": metrics["slip_score"],

                "fx": fx_ml,
                "fy": fy_ml,
                "fz": fz_ml,

                "contact": contact_state,

                "mean_dx": mean_dx,
                "mean_dy": mean_dy,
                "mean_disp": mean_disp,
                "max_disp": max_disp,

                "timestamp": time.time()
            }

            if show:
                cv2.imshow(f"Cam {cam_id}", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            yield frame, black_window, camera_state
    finally:
        picam2.close()
        if show:
            cv2.destroyAllWindows()
