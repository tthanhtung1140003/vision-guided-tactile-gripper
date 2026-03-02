#config_base.py
import numpy as np
import cv2
from copy import deepcopy

class TactileConfig:
    # ---------- Video ----------
    FRAME_SIZE = (640, 480)

    # ---------- Grid (default) ----------
    rows, cols = 5, 5
    cx0, cy0 = 177, 97
    half_size = 40
    spacing = 86
    radius = 15

    # ---------- Slip ----------
    SLIP_THRESHOLD = 2.0
    MOTION_HISTORY_LEN = 10
    ANGLE_TOL = 90
    ENTROPY_TOL = np.log(5) * 0.7
    CIRCULAR_VAR_TOL = 0.4
    MIN_CELLS_ACTIVE = 3
    MIN_MARKERS_PER_CELL = 2
    MIN_DYNAMIC_THRESH = 2.5

    # ---------- Torsion ----------
    vort_threshold = 0.05
    min_points = 3

    # ---------- Blob ----------
    @staticmethod
    def make_blob_params():
        p = cv2.SimpleBlobDetector_Params()
        p.filterByColor = True
        p.blobColor = 0
        p.filterByArea = True
        p.minArea = 500
        p.maxArea = 900
        p.filterByCircularity = True
        p.minCircularity = 0.3
        p.filterByConvexity = False
        p.filterByInertia = False
        return p

    # ---------- Tracking ----------
    alpha = 0.35
    BIG_DISP_THR = 5
    STABLE_meanMOTION = 0.03
    STABLE_maxMOTION = 0.3

    def clone(self):
        return deepcopy(self)
    
def cam1_edit(frame, zoom=0.926, dx=30, dy=20):
    h, w = frame.shape[:2] 
    M = np.float32([ 
        [zoom, 0, dx + (1 - zoom) * w / 2],
        [0, zoom, dy + (1 - zoom) * h / 2] ]) 
    frame_out = cv2.warpAffine( frame, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0) )
    return frame_out