import numpy as np

def display_params(
    ref_dots,
    aligned,
    displacements,
    angles,
    entropy,          
    vx,
    vy,
    fz,
    prev_mean_disp=None,
    file=None
):

    ref_dots = np.asarray(ref_dots, dtype=np.float32)
    aligned = np.asarray(aligned, dtype=np.float32)
    displacements = np.asarray(displacements, dtype=np.float32)
    angles = np.asarray(angles, dtype=np.float32)
    vx = np.asarray(vx, dtype=np.float32)
    vy = np.asarray(vy, dtype=np.float32)
    Cx, Cy = np.mean(aligned[:, 0]), np.mean(aligned[:, 1])
    Cx_ref, Cy_ref = np.mean(ref_dots[:, 0]), np.mean(ref_dots[:, 1])

    centroid_dx = Cx - Cx_ref
    centroid_dy = Cy - Cy_ref

    mean_disp = np.mean(displacements)
    std_disp = np.std(displacements)

    dx = aligned[:, 0] - ref_dots[:, 0]
    dy = aligned[:, 1] - ref_dots[:, 1]

    std_dx = np.std(dx)
    std_dy = np.std(dy)

    shear_anisotropy = std_dx / (std_dy + 1e-6)
    v_mag = np.hypot(vx, vy)

    mean_v_mag = np.mean(v_mag)
    std_v = np.std(v_mag)

    mean_vx = np.mean(vx)
    mean_vy = np.mean(vy)

    if len(angles) > 1:
        angles_rad = np.deg2rad(angles)
        angle_var = 1.0 - np.sqrt(
            np.mean(np.cos(angles_rad))**2 +
            np.mean(np.sin(angles_rad))**2
        )
    else:
        angle_var = 1.0

    r = np.hypot(aligned[:, 0] - Cx, aligned[:, 1] - Cy)
    r_norm = r / (np.max(r) + 1e-6)

    core_disp = np.mean(displacements[r_norm < 0.5])
    edge_disp = np.mean(displacements[r_norm >= 0.5])
    core_edge_ratio = core_disp / (edge_disp + 1e-6)

    mean_radial_disp = np.mean(r)
    std_radial_disp = np.std(r)

    if prev_mean_disp is not None:
        mean_disp_dt = mean_disp - prev_mean_disp
    else:
        mean_disp_dt = 0.0

    r_norm = r / (np.max(r) + 1e-6)
    core_disp = np.mean(displacements[r_norm < 0.5])
    edge_disp = np.mean(displacements[r_norm >= 0.5])
    core_edge_ratio = core_disp / (edge_disp + 1e-6)

    # ---- contact area ratio (GOOD FOR Fz) ----
    try:
        def polygon_area(points):
            x = points[:,0]
            y = points[:,1]
            return 0.5*np.abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))
        area_ref = polygon_area(ref_dots)
        area_cur = polygon_area(aligned)
        area_ratio = area_cur / (area_ref + 1e-6)
    except:
        area_ratio = 1.0

    
    # 8. FEATURE VECTOR (INPUT X)
    feature_vector = np.array([
        centroid_dx,
        centroid_dy,
        mean_disp,
        std_disp,
        area_ratio,
        mean_radial_disp,
        std_dx,
        std_dy,
        shear_anisotropy,
        mean_v_mag,
        std_v,
        mean_vx,
        mean_vy,
        angle_var,
        std_radial_disp,
        core_edge_ratio,
        mean_disp_dt,
        entropy
    ], dtype=np.float32)

    # 9. LABEL (OUTPUT y)
    label = np.array([fz], dtype=np.float32)

    if file is not None:
        line = " ".join(
            [f"{v:.6f}" for v in feature_vector] +
            [f"{v:.6f}" for v in label]
        )
        file.write(line + "\n")
        file.flush()

    return feature_vector, label, mean_disp
