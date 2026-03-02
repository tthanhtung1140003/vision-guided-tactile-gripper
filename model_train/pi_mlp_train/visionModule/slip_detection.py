import numpy as np
from config import *

def slip_detector(displacements, angles, motion_history, ref_points, new_points, grid_motion=None):
    # --- Shear slip part ---
    if len(displacements) == 0:
        shear_slip = False
        entropy = 0
    else:
        motions = 1.2* np.array(displacements)
        mean_motion = np.mean(motions)
        motion_history.append(mean_motion)
        if len(motion_history) > MOTION_HISTORY_LEN:
            motion_history.pop(0)

        dynamic_thresh = SLIP_THRESHOLD
        if len(motion_history) > 1:
            dynamic_thresh = np.mean(motion_history) + 1.5 * np.std(motion_history)
        dynamic_thresh = max(dynamic_thresh, MIN_DYNAMIC_THRESH)

        if len(angles) > 1:
            angles_rad = np.deg2rad(angles)
            mean_complex = np.mean(np.exp(1j * angles_rad))
            circ_var = 1 - np.abs(mean_complex)
        else:
            circ_var = 1.0
        is_uniform_circ = circ_var < CIRCULAR_VAR_TOL

        hist, _ = np.histogram(motions, bins=10)
        total = np.sum(hist)
        if total > 0:
            probs = hist / total
            probs = probs[probs > 0]
            entropy = -np.sum(probs * np.log(probs)) if len(probs) > 0 else 0
        else:
            entropy = 0
        is_coherent = entropy < ENTROPY_TOL

        active_cells = 0
        if grid_motion is not None:
            for motions_cell in grid_motion.values():
                if len(motions_cell) >= MIN_MARKERS_PER_CELL:
                    dxs, dys = zip(*motions_cell)
                    cell_motions = [np.sqrt(dx**2 + dy**2) for dx, dy in motions_cell]
                    cell_angles = [np.degrees(np.arctan2(dy, dx)) for dx, dy in motions_cell]
                    cell_mean_motion = np.mean(cell_motions)
                    if cell_mean_motion > dynamic_thresh:
                        cell_circ_var = 1 - np.abs(np.mean(np.exp(1j * np.deg2rad(cell_angles)))) if len(cell_angles) > 1 else 1.0
                        if cell_circ_var < CIRCULAR_VAR_TOL:
                            active_cells += 1
            is_partial_slip = active_cells >= MIN_CELLS_ACTIVE
        else:
            is_partial_slip = True  

        global_conditions_met = sum([mean_motion > dynamic_thresh, is_uniform_circ, is_coherent])
        total_conditions = global_conditions_met + (1 if is_partial_slip else 0)

        shear_slip = total_conditions >= 3

    # --- Torsional slip part ---
    def compute_vorticity(ref_p, new_p):
        if len(ref_p) < min_points:
            return 0.0
        ref = np.array(ref_p, dtype=float)
        new = np.array(new_p, dtype=float)
        disp = 3*(new - ref)
        u, v = disp[:,0], disp[:,1]
        x, y = ref[:,0], ref[:,1]
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
            if len(cell_disps) < min_points:
                continue
            cell_row, cell_col = cell
            cell_ref = np.array([[cell_col * cell_size + np.random.uniform(-44, 44),
                                  cell_row * cell_size + np.random.uniform(-44, 44)]
                                 for _ in cell_disps])
            cell_new = cell_ref + np.array(cell_disps)
            cell_curl = compute_vorticity(cell_ref, cell_new)
            local_curls.append(cell_curl)

    if local_curls:
        mean_local_curl = np.mean(local_curls)
        num_active = sum(1 for curl in local_curls if curl > vort_threshold)
        torsion_slip = global_curl > vort_threshold or (mean_local_curl > vort_threshold or num_active >= 2)
    else:
        torsion_slip = global_curl > vort_threshold

    # --- Combined slip state ---
    slip_state = shear_slip or torsion_slip
    return slip_state, entropy