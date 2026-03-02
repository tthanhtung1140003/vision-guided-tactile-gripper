#config.py
import numpy as np
import cv2

# Video config
FRAME_SIZE = (640, 480)

# Grid config
rows, cols = 5, 5
cx0, cy0 = 177, 97
half_size = 40
spacing = 86
radius = 15

# Shear slip detection params
SLIP_THRESHOLD = 2.0  
MOTION_HISTORY_LEN = 10
ANGLE_TOL = 45.0  
ENTROPY_TOL = np.log(5) * 0.7
CIRCULAR_VAR_TOL = 0.4  
MIN_CELLS_ACTIVE = 3  
MIN_MARKERS_PER_CELL = 2  
MIN_DYNAMIC_THRESH = 3
slip_state = False

# Torsion slip detection params
vort_threshold=0.035
min_points=3       

# SimpleBlobDetector params
params = cv2.SimpleBlobDetector_Params()
params.filterByColor = True
params.blobColor = 0 
params.filterByArea = True
params.minArea = 500
params.maxArea = 900
params.filterByCircularity = True
params.minCircularity = 0.3
params.filterByConvexity = False
params.filterByInertia = False

smoothed_centers = None
alpha = 0.4

# Update reference dots params
had_big_motion = False 
BIG_DISP_THR   = 5
STABLE_meanMOTION = 0.03
STABLE_maxMOTION = 0.3
maxOfMaxDisp = 0 
maxOfMeanDisp = 0


