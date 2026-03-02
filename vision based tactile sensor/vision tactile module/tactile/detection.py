# #detection.py
# import cv2
# import numpy as np
# from tactile.config import *
# from sklearn.neighbors import NearestNeighbors
# from tactile.config_base import TactileConfig

# def detect_dots(frame, cfg: TactileConfig):
#     global smoothed_centers, alpha

#     lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
#     l, a, b = cv2.split(lab)
#     clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
#     cl = clahe.apply(l)
#     lab_enhanced = cv2.merge((cl, a, b))
#     frame = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
#     gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#     gray = cv2.GaussianBlur(gray, (5,5), 0)
#     gray = cv2.medianBlur(gray, 7)
    

#     centers = []
#     detector = cv2.SimpleBlobDetector_create(cfg.blob_params)

#     for i in range(rows):
#         for j in range(cols):
#             cx = cx0 + j * spacing
#             cy = cy0 + i * spacing

#             x1 = max(0, cx - half_size)
#             y1 = max(0, cy - half_size)
#             x2 = min(frame.shape[1]-1, cx + half_size)
#             y2 = min(frame.shape[0]-1, cy + half_size)

#             roi = gray[y1:y2, x1:x2]

#             mean_val = np.mean(roi)
#             if mean_val < 150:
#                 factor = 170 / max(mean_val, 1)
#                 roi = cv2.convertScaleAbs(roi, alpha=factor, beta=0)

#             keypoints = detector.detect(roi)

#             if keypoints:
#                 k = max(keypoints, key=lambda kp: kp.size)
#                 x = ((k.pt[0] + x1) * 10) // 1 / 10
#                 y = ((k.pt[1] + y1) * 10) // 1 / 10
#                 centers.append([x, y])

#     centers = np.array(centers, dtype=np.float32)

#     if smoothed_centers is None or len(smoothed_centers) != len(centers):
#         smoothed_centers = centers.copy()
#     else:
#         smoothed_centers = alpha * centers + (1 - alpha) * smoothed_centers

#     return smoothed_centers


# def match_dots_knn(ref, current, max_dist=30.0):
#     if len(ref) == 0 or len(current) == 0:
#         return []
    
#     nbrs = NearestNeighbors(n_neighbors=1).fit(current)
#     distances, indices = nbrs.kneighbors(ref)
#     matches = []
#     used_current = set()

#     for i, d in enumerate(distances):
#         idx_curr = indices[i][0]
#         if d[0] < max_dist and idx_curr not in used_current:
#             matches.append((ref[i], current[idx_curr]))
#             used_current.add(idx_curr)

#     return matches

# def update_ref(lastdxdy, motions, displacements, aligned, ref_dots, had_big_motion):
#     global maxOfMaxDisp, maxOfMeanDisp
#     max_motion = np.max(motions)
#     mean_motion = np.mean(motions)
#     mean_disp = np.mean(displacements)
#     max_disp = np.max(displacements)

#     if max_disp > maxOfMaxDisp :
#         maxOfMaxDisp = max_disp
#     if mean_disp > maxOfMeanDisp :
#         maxOfMeanDisp = mean_disp
    
#     if max_disp > BIG_DISP_THR:
#         had_big_motion = True

#     if had_big_motion:
#         if (mean_motion < STABLE_meanMOTION or max_motion < STABLE_maxMOTION )and (max_disp < 0.2*maxOfMaxDisp or mean_disp < 0.2*maxOfMeanDisp) :
#             ref_dots = aligned.copy()
#             had_big_motion = False
#             lastdxdy = np.zeros_like(lastdxdy)
#             maxOfMaxDisp = 0
#             maxOfMeanDisp = 0

#     return ref_dots, had_big_motion, lastdxdy

# def draw_motion(frame, ref_pt, x, y, dx, dy):
#     top_left = (int(ref_pt[0] - 2*radius), int(ref_pt[1] - 2*radius))
#     bottom_right = (int(ref_pt[0] + 2*radius), int(ref_pt[1] + 2*radius))
#     end_point = (int(ref_pt[0] + (1+abs(dx/2))*dx), int(ref_pt[1] + (1+abs(dy/2))*dy))
#     text = f"({dx:.2f},{dy:.2f})"
#     text_pos = (top_left[0], top_left[1] - 5)

#     cv2.arrowedLine(frame, (int(ref_pt[0]), int(ref_pt[1])), end_point, (0, 0, 255), 2, tipLength=0.3)
#     cv2.circle(frame, (int(x), int(y)), 3, (255, 0, 0), -1)
#     cv2.circle(frame, end_point, radius, (0, 0, 225), 1)
#     cv2.rectangle(frame, top_left, bottom_right, (0,0,255), 1)
#     cv2.putText(frame, text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)


# detection.py
import cv2
import numpy as np
from sklearn.neighbors import NearestNeighbors
from tactile.config_base import TactileConfig

# =========================
# Global smoothing state (per process)
# =========================
_smoothed_centers = None


# =========================
# Dot detection
# =========================
def detect_dots(frame, cfg: TactileConfig):
    """
    Detect tactile markers using camera-specific configuration.
    """
    global _smoothed_centers

    # ---------- Preprocess ----------
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)

    lab_enhanced = cv2.merge((cl, a, b))
    frame = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gray = cv2.medianBlur(gray, 7)

    # ---------- Blob detector ----------
    detector = cv2.SimpleBlobDetector_create(cfg.blob_params)

    centers = []

    for i in range(cfg.rows):
        for j in range(cfg.cols):
            cx = cfg.cx0 + j * cfg.spacing
            cy = cfg.cy0 + i * cfg.spacing

            x1 = max(0, int(cx - cfg.half_size))
            y1 = max(0, int(cy - cfg.half_size))
            x2 = min(frame.shape[1] - 1, int(cx + cfg.half_size))
            y2 = min(frame.shape[0] - 1, int(cy + cfg.half_size))

            roi = gray[y1:y2, x1:x2]

            if roi.size == 0:
                continue

            mean_val = np.mean(roi)
            if mean_val < 150:
                factor = 170 / max(mean_val, 1)
                roi = cv2.convertScaleAbs(roi, alpha=factor, beta=0)

            keypoints = detector.detect(roi)

            if keypoints:
                k = max(keypoints, key=lambda kp: kp.size)
                x = round(k.pt[0] + x1, 1)
                y = round(k.pt[1] + y1, 1)
                centers.append([x, y])
            

    centers = np.array(centers, dtype=np.float32)

    # ---------- Temporal smoothing ----------
    if _smoothed_centers is None or len(_smoothed_centers) != len(centers):
        _smoothed_centers = centers.copy()
    else:
        _smoothed_centers = (
            cfg.alpha * centers + (1.0 - cfg.alpha) * _smoothed_centers
        )

    return _smoothed_centers

# =========================
# Dot matching
# =========================
def match_dots_knn(ref, current, max_dist=30.0):
    if len(ref) == 0 or len(current) == 0:
        return []

    nbrs = NearestNeighbors(n_neighbors=1).fit(current)
    distances, indices = nbrs.kneighbors(ref)

    matches = []
    used_current = set()

    for i, d in enumerate(distances):
        idx_curr = indices[i][0]
        if d[0] < max_dist and idx_curr not in used_current:
            matches.append((ref[i], current[idx_curr]))
            used_current.add(idx_curr)

    return matches


# =========================
# Reference update logic
# =========================
def update_ref(lastdxdy, motions, displacements, aligned, ref_dots, had_big_motion, cfg: TactileConfig):
    max_motion = np.max(motions)
    mean_motion = np.mean(motions)
    mean_disp = np.mean(displacements)
    max_disp = np.max(displacements)

    if max_disp > cfg.BIG_DISP_THR:
        had_big_motion = True

    if had_big_motion:
        if (
            (mean_motion < cfg.STABLE_meanMOTION or max_motion < cfg.STABLE_maxMOTION)
            and max_disp < 0.2 * max(lastdxdy.max(), 1e-6)
        ):
            ref_dots = aligned.copy()
            had_big_motion = False
            lastdxdy = np.zeros_like(lastdxdy)

    return ref_dots, had_big_motion, lastdxdy


# =========================
# Visualization
# =========================
def draw_motion(frame, ref_pt, x, y, dx, dy, cfg: TactileConfig):
    r = cfg.radius

    top_left = (int(ref_pt[0] - 2 * r), int(ref_pt[1] - 2 * r))
    bottom_right = (int(ref_pt[0] + 2 * r), int(ref_pt[1] + 2 * r))

    end_point = (
        int(ref_pt[0] + (1 + abs(dx / 2)) * dx),
        int(ref_pt[1] + (1 + abs(dy / 2)) * dy),
    )

    text = f"({dx:.2f},{dy:.2f})"
    text_pos = (top_left[0], top_left[1] - 5)

    cv2.arrowedLine(frame, tuple(ref_pt.astype(int)), end_point, (0, 0, 255), 2)
    cv2.circle(frame, (int(x), int(y)), 3, (255, 0, 0), -1)
    cv2.circle(frame, end_point, r, (0, 0, 225), 1)
    cv2.rectangle(frame, top_left, bottom_right, (0, 0, 255), 1)
    cv2.putText(frame, text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

def compute_dot_count(grid, initial_cell_areas, initial_cell_centers):

    cell_areas = np.zeros((4, 4))
    current_centers = np.zeros((4, 4, 2))

    # ===== TÍNH DIỆN TÍCH 16 Ô =====
    for i in range(4):
        for j in range(4):

            p1 = grid[i, j]
            p2 = grid[i, j+1]
            p3 = grid[i+1, j+1]
            p4 = grid[i+1, j]

            A1 = 0.5 * abs(
                p1[0]*(p2[1]-p3[1]) +
                p2[0]*(p3[1]-p1[1]) +
                p3[0]*(p1[1]-p2[1])
            )

            A2 = 0.5 * abs(
                p1[0]*(p3[1]-p4[1]) +
                p3[0]*(p4[1]-p1[1]) +
                p4[0]*(p1[1]-p3[1])
            )

            area = A1 + A2
            cell_areas[i, j] = area

            cx = int((p1[0] + p2[0] + p3[0] + p4[0]) / 4)
            cy = int((p1[1] + p2[1] + p3[1] + p4[1]) / 4)
            current_centers[i, j] = [cx, cy]

    # ===== LƯU FRAME ĐẦU =====
    if initial_cell_areas is None:
        initial_cell_areas = cell_areas.copy()
        initial_cell_centers = current_centers.copy()

    # ===== TẠO BLACK WINDOW =====
    black_window = np.zeros((480, 640, 3), dtype=np.uint8)

    dot_count = 0

    # ===== CHỈ HIỆN / ẨN CHẤM =====
    for i in range(4):
        for j in range(4):

            delta_area = cell_areas[i, j] - initial_cell_areas[i, j]

            # dùng tâm BAN ĐẦU
            cx = int(initial_cell_centers[i, j][0])
            cy = int(initial_cell_centers[i, j][1])

            # > 400 → chấm to
            if delta_area > 400:
                cv2.circle(black_window, (cx, cy), 12, (255, 255, 255), -1)
                dot_count += 2

            # > 150 → chấm nhỏ
            elif delta_area > 150:
                cv2.circle(black_window, (cx, cy), 6, (255, 255, 255), -1)
                dot_count += 1

    return dot_count, initial_cell_areas, initial_cell_centers, black_window
