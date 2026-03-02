import numpy as np
from tactile.config_base import TactileConfig

def slip_detector_quantitative1(
    displacements,
    angles,
    motion_history,
    ref_points,
    new_points,
    grid_motion=None,
    cfg: TactileConfig = None
):

    if cfg is None:
        raise ValueError("cfg (TactileConfig) must be provided")
    
    if len(displacements) == 0:
        return {
            "slip_score": 0.0,
            "shear_score": 0.0,
            "torsion_score": 0.0,
            "motion_score": 0.0,
            "circ_score": 0.0,
            "entropy_score": 0.0,
            "spatial_score": 0.0,
            "entropy": 0.0
        }

    motions = 1.2 * np.array(displacements)
    mean_motion = np.mean(motions)

    motion_history.append(mean_motion)
    if len(motion_history) > cfg.MOTION_HISTORY_LEN:
        motion_history.pop(0)

    dynamic_thresh = cfg.SLIP_THRESHOLD
    if len(motion_history) > 1:
        dynamic_thresh = np.mean(motion_history) + 1.5 * np.std(motion_history)
    dynamic_thresh = max(dynamic_thresh, cfg.MIN_DYNAMIC_THRESH)

    motion_score = np.clip(
        (mean_motion - dynamic_thresh) / dynamic_thresh,
        0.0, 1.0
    )

    if len(angles) > 1:
        angles_rad = np.deg2rad(angles)
        mean_complex = np.mean(np.exp(1j * angles_rad))
        circ_var = 1 - np.abs(mean_complex)
    else:
        circ_var = 1.0

    circ_score = np.clip(
        1.0 - circ_var / cfg.CIRCULAR_VAR_TOL,
        0.0, 1.0
    )

    hist, _ = np.histogram(motions, bins=10)
    total = np.sum(hist)

    if total > 0:
        probs = hist / total
        probs = probs[probs > 0]
        entropy = -np.sum(probs * np.log(probs)) if len(probs) > 0 else 0.0
    else:
        entropy = 0.0

    entropy_score = np.clip(
        1.0 - entropy / cfg.ENTROPY_TOL,
        0.0, 1.0
    )

    active_cells = 0

    if grid_motion is not None:
        for motions_cell in grid_motion.values():
            if len(motions_cell) < cfg.MIN_MARKERS_PER_CELL:
                continue

            dxs, dys = zip(*motions_cell)
            cell_motions = np.sqrt(np.array(dxs) ** 2 + np.array(dys) ** 2)
            cell_angles = np.degrees(np.arctan2(dys, dxs))

            cell_mean_motion = np.mean(cell_motions)

            if cell_mean_motion > dynamic_thresh:
                if len(cell_angles) > 1:
                    cell_circ_var = 1 - np.abs(
                        np.mean(np.exp(1j * np.deg2rad(cell_angles)))
                    )
                else:
                    cell_circ_var = 1.0

                if cell_circ_var < cfg.CIRCULAR_VAR_TOL:
                    active_cells += 1

        spatial_score = np.clip(
            active_cells / cfg.MIN_CELLS_ACTIVE,
            0.0, 1.0
        )
    else:
        spatial_score = 0.5

    shear_score = (
        0.35 * motion_score +
        0.25 * circ_score +
        0.25 * entropy_score +
        0.15 * spatial_score
    )

    def compute_vorticity(ref_p, new_p):
        if len(ref_p) < cfg.min_points:
            return 0.0

        ref = np.array(ref_p, dtype=float)
        new = np.array(new_p, dtype=float)

        disp = 3.0 * (new - ref)
        u, v = disp[:, 0], disp[:, 1]
        x, y = ref[:, 0], ref[:, 1]

        A = np.column_stack([x, y, np.zeros_like(x), np.zeros_like(x)])
        A2 = np.column_stack([np.zeros_like(x), np.zeros_like(x), x, y])
        A = np.vstack([A, A2])
        b = np.concatenate([u, v])

        params, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        a, b_coef, c, d = params

        return abs(c - b_coef)

    global_curl = compute_vorticity(ref_points, new_points)

    local_curls = []
    if grid_motion is not None:
        cell_size = 88  
        for cell, cell_disps in grid_motion.items():
            if len(cell_disps) < cfg.min_points:
                continue

            cell_row, cell_col = cell
            cell_ref = np.array([
                [
                    cell_col * cell_size + np.random.uniform(-44, 44),
                    cell_row * cell_size + np.random.uniform(-44, 44)
                ]
                for _ in cell_disps
            ])
            cell_new = cell_ref + np.array(cell_disps)
            cell_curl = compute_vorticity(cell_ref, cell_new)
            local_curls.append(cell_curl)

    torsion_score = np.clip(
        global_curl / cfg.vort_threshold,
        0.0, 1.0
    )

    if local_curls:
        local_score = np.clip(
            np.mean(local_curls) / cfg.vort_threshold,
            0.0, 1.0
        )
        torsion_score = max(torsion_score, local_score)

    slip_score = max(shear_score, torsion_score)

    return {
        "slip_score": slip_score,
        "shear_score": shear_score,
        "torsion_score": torsion_score,
        "motion_score": motion_score,
        "circ_score": circ_score,
        "entropy_score": entropy_score,
        "spatial_score": spatial_score,
        "entropy": entropy,
        "mean_motion": mean_motion,
        "dynamic_thresh": dynamic_thresh
    }
