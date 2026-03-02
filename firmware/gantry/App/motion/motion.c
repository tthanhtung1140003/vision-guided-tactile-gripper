#include "motion/motion.h"
#include "driver/driver.h"
#include "system/system.h"
#include "error/error.h"
#include "tim.h"
#include "comm/comm.h"

#include <math.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

/* ================= MECH CONFIG ================= */
#define STEPS_PER_MM_X   120.0f
#define STEPS_PER_MM_Y   40.0f
#define STEPS_PER_MM_Z   800.0f

/* ================= WORKSPACE SOFT LIMITS (0 at MIN) =================
 * NOTE: Synced with GUI default limits (GUIv10.py SLIDER_MAX).
 * If you change GUI limits, update these to match to avoid UI/FW mismatch.
 */
#define WS_X_MIN_MM   0.0f
#define WS_X_MAX_MM   350.0f
#define WS_Y_MIN_MM   0.0f
#define WS_Y_MAX_MM   300.0f
#define WS_Z_MIN_MM   0.0f
#define WS_Z_MAX_MM   120.0f

/* ================= TRACKING (TVEL) PER-AXIS SPEED CAPS =================
 * Clamp commanded velocity per axis (mm/s) for safety + predictable behavior.
 * These caps apply ONLY to TVEL mode, not MOVE.
 */
#define TVEL_CAP_X_MMPS   40.0f
#define TVEL_CAP_Y_MMPS   40.0f
#define TVEL_CAP_Z_MMPS   20.0f

static bool s_homed = false;
static bool s_soft_limits_enabled = true;

#define MOTION_MIN_STEP_HZ   50.0f
#define MOTION_MAX_STEP_HZ   20000.0f

static volatile int32_t pos_steps_x = 0;
static volatile int32_t pos_steps_y = 0;
static volatile int32_t pos_steps_z = 0;

static int32_t s_ws_x_min_steps = 0, s_ws_x_max_steps = 0;
static int32_t s_ws_y_min_steps = 0, s_ws_y_max_steps = 0;
static int32_t s_ws_z_min_steps = 0, s_ws_z_max_steps = 0;

static int32_t tgt_steps_x = 0;
static int32_t tgt_steps_y = 0;
static int32_t tgt_steps_z = 0;

/* ================= SPEED/ACCEL ================= */
static float target_speed  = 120.0f;
static volatile float s_job_target_speed = 120.0f;
static float current_speed = 0.0f;
static float accel         = 100.0f;
static volatile uint32_t s_step_hz_last = 0;

/* ================= STEPPING DATA ================= */
static int32_t abs_x, abs_y, abs_z;
static int32_t cnt_x, cnt_y, cnt_z;
static int32_t err_x, err_y, err_z;
static int32_t max_steps;
static float   major_spm;
static int32_t dda_ticks;

/* ================= FLAGS ================= */
static volatile bool motion_active = false;
static volatile bool motion_done_flag = false;
static uint16_t enable_delay_ms = 0;

/* ================= TRACKING VELOCITY MODE (TVEL) =================
 * Uses TIM2 stepping ISR with a fixed base frequency and DDA phase accumulators.
 * - Commanded velocity is latched and must be refreshed (watchdog).
 * - Velocity is ramped by the existing accel setting (mm/s^2).
 * - Soft limits are enforced (0..max) when homed.
 */
static volatile bool s_track_active = false;
static volatile bool s_track_timer_running = false;
static volatile uint32_t s_track_base_hz = 10000u; /* default base step tick (higher => smoother) */
static volatile uint32_t s_track_last_cmd_ms = 0u;
static volatile uint32_t s_track_watchdog_ms = 500u; /* tolerate UART jitter; GUI sends heartbeat */

static volatile float s_track_cmd_vx = 0.0f, s_track_cmd_vy = 0.0f, s_track_cmd_vz = 0.0f; /* mm/s */
static volatile float s_track_cur_vx = 0.0f, s_track_cur_vy = 0.0f, s_track_cur_vz = 0.0f; /* mm/s */

static volatile float s_track_phase_x = 0.0f;
static volatile float s_track_phase_y = 0.0f;
static volatile float s_track_phase_z = 0.0f;

static inline float f_clamp(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* forward decl to avoid implicit declaration */
static inline void Motion_TIM2_SetHz_Safe(uint32_t hz);


static inline void track_timer_start(void)
{
    if (s_track_timer_running) return;
    /* keep drivers enabled while tracking */
    Driver_Enable_All();
    s_step_hz_last = s_track_base_hz;
    Motion_TIM2_SetHz_Safe(s_step_hz_last);
    HAL_TIM_Base_Start_IT(&htim2);
    s_track_timer_running = true;
    Comm_SetMotionActive(true);
}

static inline void track_timer_stop(void)
{
    if (!s_track_timer_running) return;
    HAL_TIM_Base_Stop_IT(&htim2);
    Driver_Disable_All();
    s_step_hz_last = 0;
    s_track_timer_running = false;
    Comm_SetMotionActive(false);
}

static inline float f_abs(float v) { return (v < 0) ? -v : v; }
static inline float f_max3(float a, float b, float c)
{
    float m = (a > b) ? a : b;
    return (m > c) ? m : c;
}

static inline void clamp_step_hz(float *hz)
{
    if (*hz < 1.0f) *hz = 1.0f;
    if (*hz > MOTION_MAX_STEP_HZ) *hz = MOTION_MAX_STEP_HZ;
}

static inline bool in_range(float v, float lo, float hi)
{
    return (v >= lo) && (v <= hi);
}

/* ===== TIM2 frequency update safe helper =====
 * Tránh “nhảy pha” khi đổi ARR/PSC trong lúc đang chạy:
 * - gọi TIM2_Set_Frequency()
 * - reset CNT về 0
 * - clear update flag
 *
 * Lưu ý: TIM2_Set_Frequency() nằm trong tim.c của bạn.
 */
static inline void Motion_TIM2_SetHz_Safe(uint32_t hz)
{
    if (hz == 0u) return;

    TIM2_Set_Frequency(hz);

    /* reset counter để nhịp mới bắt đầu sạch -> giảm giật */
    __HAL_TIM_SET_COUNTER(&htim2, 0u);
    __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
}

/* ================= NEW API: homed + soft limits ================= */
void Motion_SetHomed(bool homed)
{
    s_homed = homed;
}

bool Motion_IsHomed(void)
{
    return s_homed;
}

void Motion_EnableSoftLimits(bool enable)
{
    s_soft_limits_enabled = enable;
}

void Motion_Init(void)
{
    motion_active = false;
    motion_done_flag = false;
    current_speed = 0.0f;
    enable_delay_ms = 0;
    dda_ticks = 0;
    s_job_target_speed = target_speed;

    s_homed = false;
    s_soft_limits_enabled = true;

    /* Precompute soft-limit steps for fast checks (used by tracking ISR). */
    s_ws_x_min_steps = (int32_t)lroundf(WS_X_MIN_MM * STEPS_PER_MM_X);
    s_ws_x_max_steps = (int32_t)lroundf(WS_X_MAX_MM * STEPS_PER_MM_X);
    s_ws_y_min_steps = (int32_t)lroundf(WS_Y_MIN_MM * STEPS_PER_MM_Y);
    s_ws_y_max_steps = (int32_t)lroundf(WS_Y_MAX_MM * STEPS_PER_MM_Y);
    s_ws_z_min_steps = (int32_t)lroundf(WS_Z_MIN_MM * STEPS_PER_MM_Z);
    s_ws_z_max_steps = (int32_t)lroundf(WS_Z_MAX_MM * STEPS_PER_MM_Z);

    s_step_hz_last = 0;
    Comm_SetMotionActive(false);

    s_track_active = false;
    s_track_timer_running = false;
    s_track_last_cmd_ms = 0u;
    s_track_cmd_vx = s_track_cmd_vy = s_track_cmd_vz = 0.0f;
    s_track_cur_vx = s_track_cur_vy = s_track_cur_vz = 0.0f;
    s_track_phase_x = s_track_phase_y = s_track_phase_z = 0.0f;
}

void Motion_SetSpeed(float vx, float vy, float vz)
{
    float v = f_max3(f_abs(vx), f_abs(vy), f_abs(vz));
    if (v < 1.0f) v = 1.0f;
    target_speed = v;
}

float Motion_GetSpeedSetting(void)
{
    return target_speed;
}

void Motion_SetAcceleration(float accel_mm_s2)
{
    if (accel_mm_s2 < 1.0f) accel_mm_s2 = 1.0f;
    accel = accel_mm_s2;
}

float Motion_GetAcceleration(void)
{
    return accel;
}

void Motion_SetPosition(float x, float y, float z)
{
    pos_steps_x = (int32_t)lroundf(x * STEPS_PER_MM_X);
    pos_steps_y = (int32_t)lroundf(y * STEPS_PER_MM_Y);
    pos_steps_z = (int32_t)lroundf(z * STEPS_PER_MM_Z);
}

void Motion_GetPosition(float *x, float *y, float *z)
{
    if (x) *x = ((float)pos_steps_x) / STEPS_PER_MM_X;
    if (y) *y = ((float)pos_steps_y) / STEPS_PER_MM_Y;
    if (z) *z = ((float)pos_steps_z) / STEPS_PER_MM_Z;
}

void Motion_GetAxisSpeeds(float *vx, float *vy, float *vz)
{
    float sx = 0.0f, sy = 0.0f, sz = 0.0f;

    /* Velocity mode (tracking) reports commanded/ramped velocities directly */
    if (s_track_active)
    {
        sx = s_track_cur_vx;
        sy = s_track_cur_vy;
        sz = s_track_cur_vz;
        if (vx) *vx = sx;
        if (vy) *vy = sy;
        if (vz) *vz = sz;
        #undef AT_MAX
        #undef AT_MIN
        #undef CAN_STEP_POS
        #undef CAN_STEP_NEG
        #undef CLAMP_AXIS_VEL

        return;
    }

    if (motion_active && (enable_delay_ms == 0) && (max_steps > 0) && (s_step_hz_last > 0))
    {
        const float step_hz = (float)s_step_hz_last;

        if (abs_x > 0)
        {
            sx = (step_hz * ((float)abs_x / (float)max_steps)) / STEPS_PER_MM_X;
            if (!Driver_IsDirPositive(AXIS_X)) sx = -sx;
        }
        if (abs_y > 0)
        {
            sy = (step_hz * ((float)abs_y / (float)max_steps)) / STEPS_PER_MM_Y;
            if (!Driver_IsDirPositive(AXIS_Y)) sy = -sy;
        }
        if (abs_z > 0)
        {
            sz = (step_hz * ((float)abs_z / (float)max_steps)) / STEPS_PER_MM_Z;
            if (!Driver_IsDirPositive(AXIS_Z)) sz = -sz;
        }
    }

    if (vx) *vx = sx;
    if (vy) *vy = sy;
    if (vz) *vz = sz;
}

void Motion_MoveTo(bool use_x, bool use_y, bool use_z, float x, float y, float z)
{
    /* Any absolute move cancels tracking velocity mode */
    if (s_track_active)
    {
        Motion_Track_Stop();
    }
    /* ===== Soft limits (chỉ khi đã homed và không phải homing nội bộ) ===== */
    if (s_soft_limits_enabled && s_homed && (System_State_Get() != SYS_HOMING))
    {
        if (use_x && !in_range(x, WS_X_MIN_MM, WS_X_MAX_MM))
        {
            System_Log(LOG_WARN, "SOFT_LIMIT: X out of range");
            Error_Set(ERR_LIMIT);
            return;
        }
        if (use_y && !in_range(y, WS_Y_MIN_MM, WS_Y_MAX_MM))
        {
            System_Log(LOG_WARN, "SOFT_LIMIT: Y out of range");
            Error_Set(ERR_LIMIT);
            return;
        }
        if (use_z && !in_range(z, WS_Z_MIN_MM, WS_Z_MAX_MM))
        {
            System_Log(LOG_WARN, "SOFT_LIMIT: Z out of range");
            Error_Set(ERR_LIMIT);
            return;
        }
    }

    /* Target theo STEP (absolute) */
    tgt_steps_x = use_x ? (int32_t)lroundf(x * STEPS_PER_MM_X) : (int32_t)pos_steps_x;
    tgt_steps_y = use_y ? (int32_t)lroundf(y * STEPS_PER_MM_Y) : (int32_t)pos_steps_y;
    tgt_steps_z = use_z ? (int32_t)lroundf(z * STEPS_PER_MM_Z) : (int32_t)pos_steps_z;

    /* Delta step */
    int32_t dx = tgt_steps_x - (int32_t)pos_steps_x;
    int32_t dy = tgt_steps_y - (int32_t)pos_steps_y;
    int32_t dz = tgt_steps_z - (int32_t)pos_steps_z;

    Driver_SetDir(AXIS_X, (dx >= 0));
    Driver_SetDir(AXIS_Y, (dy >= 0));
    Driver_SetDir(AXIS_Z, (dz >= 0));

    abs_x = (dx >= 0) ? dx : -dx;
    abs_y = (dy >= 0) ? dy : -dy;
    abs_z = (dz >= 0) ? dz : -dz;

    cnt_x = cnt_y = cnt_z = 0;
    err_x = err_y = err_z = 0;

    max_steps = abs_x;
    major_spm = STEPS_PER_MM_X;
    if (abs_y > max_steps) { max_steps = abs_y; major_spm = STEPS_PER_MM_Y; }
    if (abs_z > max_steps) { max_steps = abs_z; major_spm = STEPS_PER_MM_Z; }

    dda_ticks = 0;

    /* Nếu không có bước nào -> không chạy timer, coi như done */
    if (max_steps <= 0)
    {
        motion_active = false;
        motion_done_flag = false;
        enable_delay_ms = 0;

        s_step_hz_last = 0;

        System_Log(LOG_INFO, "Motion skip (0 steps)");
        System_NotifyMotionDone();
        return;
    }

    s_job_target_speed = target_speed;
    current_speed = 0.0f;
    motion_done_flag = false;
    motion_active = true;

    enable_delay_ms = 2;

    Driver_Enable_All();

    /* Bật chế độ “motion active” để comm tự giảm log khi đang chạy */
    Comm_SetMotionActive(true);

    /* Start với step_hz rất nhỏ để tránh giật */
    s_step_hz_last = 1u;
    Motion_TIM2_SetHz_Safe(s_step_hz_last);

    HAL_TIM_Base_Start_IT(&htim2);
    System_Log(LOG_INFO, "Motion start");
}

void Motion_Tick_1ms(void)
{
    /* ===== Tracking velocity mode ===== */
    if (s_track_active)
    {
        uint32_t now = HAL_GetTick();

        /* Watchdog: if no TVEL refresh, command -> 0 */
        if ((s_track_last_cmd_ms > 0u) && ((now - s_track_last_cmd_ms) > s_track_watchdog_ms))
        {
            s_track_cmd_vx = 0.0f;
            s_track_cmd_vy = 0.0f;
            s_track_cmd_vz = 0.0f;
        }

        /* Soft limit clamp (only when homed) */
        if (s_soft_limits_enabled && s_homed && (System_State_Get() != SYS_HOMING))
        {
            float x = ((float)pos_steps_x) / STEPS_PER_MM_X;
            float y = ((float)pos_steps_y) / STEPS_PER_MM_Y;
            float z = ((float)pos_steps_z) / STEPS_PER_MM_Z;

            if ((x <= WS_X_MIN_MM + 1e-3f) && (s_track_cmd_vx < 0.0f)) s_track_cmd_vx = 0.0f;
            if ((x >= WS_X_MAX_MM - 1e-3f) && (s_track_cmd_vx > 0.0f)) s_track_cmd_vx = 0.0f;
            if ((y <= WS_Y_MIN_MM + 1e-3f) && (s_track_cmd_vy < 0.0f)) s_track_cmd_vy = 0.0f;
            if ((y >= WS_Y_MAX_MM - 1e-3f) && (s_track_cmd_vy > 0.0f)) s_track_cmd_vy = 0.0f;
            if ((z <= WS_Z_MIN_MM + 1e-3f) && (s_track_cmd_vz < 0.0f)) s_track_cmd_vz = 0.0f;
            if ((z >= WS_Z_MAX_MM - 1e-3f) && (s_track_cmd_vz > 0.0f)) s_track_cmd_vz = 0.0f;
        }

        /* Accel-limited ramp (per axis) using existing accel setting */
        float dv = accel * 0.001f;
        if (dv < 0.001f) dv = 0.001f;

        float tvx = s_track_cmd_vx;
        float tvy = s_track_cmd_vy;
        float tvz = s_track_cmd_vz;

        /* limit maximum speed by existing target_speed (mm/s) */
        float vmax = target_speed;
        if (vmax < 1.0f) vmax = 1.0f;
        tvx = f_clamp(tvx, -vmax, vmax);
        tvy = f_clamp(tvy, -vmax, vmax);
        tvz = f_clamp(tvz, -vmax, vmax);

        #define RAMP_ONE(cur, tgt) do { \
            if ((cur) < (tgt)) { (cur) += dv; if ((cur) > (tgt)) (cur) = (tgt); } \
            else if ((cur) > (tgt)) { (cur) -= dv; if ((cur) < (tgt)) (cur) = (tgt); } \
        } while(0)

        RAMP_ONE(s_track_cur_vx, tvx);
        RAMP_ONE(s_track_cur_vy, tvy);
        RAMP_ONE(s_track_cur_vz, tvz);

        #undef RAMP_ONE

        /* Keep timer running continuously while tracking is active.
           Starting/stopping timers and disabling drivers causes perceived "đứt đoạn".
           When velocity ~0, ISR simply won't emit steps. */
        track_timer_start();

        return;
    }

    if (!motion_active) return;

    if (enable_delay_ms)
    {
        enable_delay_ms--;
        return;
    }

    int32_t remaining_steps = (max_steps - dda_ticks);
    if (remaining_steps < 0) remaining_steps = 0;

    float remaining_mm = (major_spm > 0.0f) ? ((float)remaining_steps / major_spm) : 0.0f;

    float v_brake = sqrtf(2.0f * accel * remaining_mm);

    float v_target = (float)s_job_target_speed;
    if (v_target > v_brake) v_target = v_brake;

    float dv = accel * 0.001f;
    if (current_speed < v_target)
    {
        current_speed += dv;
        if (current_speed > v_target) current_speed = v_target;
    }
    else
    {
        current_speed -= dv;
        if (current_speed < v_target) current_speed = v_target;
    }

    if (current_speed < 0.0f) current_speed = 0.0f;

    float step_hz_f = current_speed * major_spm;
    clamp_step_hz(&step_hz_f);

    uint32_t step_hz = (uint32_t)step_hz_f;
    if (step_hz < 1u) step_hz = 1u;

    /* Chỉ update khi có thay đổi -> giảm jitter do update ARR quá dày */
    if (step_hz != s_step_hz_last)
    {
        s_step_hz_last = step_hz;
        Motion_TIM2_SetHz_Safe(step_hz);
    }
}

void Motion_Step_ISR(void)
{
    /* ===== Tracking velocity stepping ===== */
    if (s_track_active)
    {
        if (!s_track_timer_running) return;

        /* Convert mm/s -> steps per base tick and integrate with phase accumulators */
        float sx = (s_track_cur_vx * STEPS_PER_MM_X) / (float)s_track_base_hz;
        float sy = (s_track_cur_vy * STEPS_PER_MM_Y) / (float)s_track_base_hz;
        float sz = (s_track_cur_vz * STEPS_PER_MM_Z) / (float)s_track_base_hz;

        s_track_phase_x += sx;
        s_track_phase_y += sy;
        s_track_phase_z += sz;

        /* Hard guard: prevent emitting steps beyond soft limits (tracking mode)
           Without this, the UI can clamp at max while motors keep stepping physically. */
        #define AT_MAX(ps, maxs) ((ps) >= (maxs))
        #define AT_MIN(ps, mins) ((ps) <= (mins))
        #define CAN_STEP_POS(axis_ps, axis_max) (!(s_soft_limits_enabled && s_homed) || !AT_MAX((axis_ps), (axis_max)))
        #define CAN_STEP_NEG(axis_ps, axis_min) (!(s_soft_limits_enabled && s_homed) || !AT_MIN((axis_ps), (axis_min)))
        #define CLAMP_AXIS_VEL(axis_cmd, axis_cur) do { (axis_cmd) = 0.0f; (axis_cur) = 0.0f; } while(0)

        /* Step when accumulator crosses +/-1.0 */
        while (s_track_phase_x >= 1.0f)
        {
            if (!CAN_STEP_POS(pos_steps_x, s_ws_x_max_steps)) {
                s_track_phase_x = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vx, s_track_cur_vx);
                break;
            }
            Driver_SetDir(AXIS_X, true);
            Driver_Step_Axis(AXIS_X);
            pos_steps_x += 1;
            s_track_phase_x -= 1.0f;
        }
        while (s_track_phase_x <= -1.0f)
        {
            if (!CAN_STEP_NEG(pos_steps_x, s_ws_x_min_steps)) {
                s_track_phase_x = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vx, s_track_cur_vx);
                break;
            }
            Driver_SetDir(AXIS_X, false);
            Driver_Step_Axis(AXIS_X);
            pos_steps_x -= 1;
            s_track_phase_x += 1.0f;
        }

        while (s_track_phase_y >= 1.0f)
        {
            if (!CAN_STEP_POS(pos_steps_y, s_ws_y_max_steps)) {
                s_track_phase_y = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vy, s_track_cur_vy);
                break;
            }
            Driver_SetDir(AXIS_Y, true);
            Driver_Step_Axis(AXIS_Y);
            pos_steps_y += 1;
            s_track_phase_y -= 1.0f;
        }
        while (s_track_phase_y <= -1.0f)
        {
            if (!CAN_STEP_NEG(pos_steps_y, s_ws_y_min_steps)) {
                s_track_phase_y = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vy, s_track_cur_vy);
                break;
            }
            Driver_SetDir(AXIS_Y, false);
            Driver_Step_Axis(AXIS_Y);
            pos_steps_y -= 1;
            s_track_phase_y += 1.0f;
        }

        while (s_track_phase_z >= 1.0f)
        {
            if (!CAN_STEP_POS(pos_steps_z, s_ws_z_max_steps)) {
                s_track_phase_z = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vz, s_track_cur_vz);
                break;
            }
            Driver_SetDir(AXIS_Z, true);
            Driver_Step_Axis(AXIS_Z);
            pos_steps_z += 1;
            s_track_phase_z -= 1.0f;
        }
        while (s_track_phase_z <= -1.0f)
        {
            if (!CAN_STEP_NEG(pos_steps_z, s_ws_z_min_steps)) {
                s_track_phase_z = 0.0f;
                CLAMP_AXIS_VEL(s_track_cmd_vz, s_track_cur_vz);
                break;
            }
            Driver_SetDir(AXIS_Z, false);
            Driver_Step_Axis(AXIS_Z);
            pos_steps_z -= 1;
            s_track_phase_z += 1.0f;
        }

        return;
    }

    if (!motion_active) return;
    if (enable_delay_ms) return;

    dda_ticks++;

    if (cnt_x < abs_x)
    {
        err_x += abs_x;
        if (err_x >= max_steps)
        {
            Driver_Step_Axis(AXIS_X);
            err_x -= max_steps;
            cnt_x++;

            pos_steps_x += (Driver_IsDirPositive(AXIS_X) ? 1 : -1);
        }
    }

    if (cnt_y < abs_y)
    {
        err_y += abs_y;
        if (err_y >= max_steps)
        {
            Driver_Step_Axis(AXIS_Y);
            err_y -= max_steps;
            cnt_y++;

            pos_steps_y += (Driver_IsDirPositive(AXIS_Y) ? 1 : -1);
        }
    }

    if (cnt_z < abs_z)
    {
        err_z += abs_z;
        if (err_z >= max_steps)
        {
            Driver_Step_Axis(AXIS_Z);
            err_z -= max_steps;
            cnt_z++;

            pos_steps_z += (Driver_IsDirPositive(AXIS_Z) ? 1 : -1);
        }
    }

    if (cnt_x >= abs_x && cnt_y >= abs_y && cnt_z >= abs_z)
    {
        motion_active = false;
        motion_done_flag = true;

        HAL_TIM_Base_Stop_IT(&htim2);
        Driver_Disable_All();

        pos_steps_x = tgt_steps_x;
        pos_steps_y = tgt_steps_y;
        pos_steps_z = tgt_steps_z;

        s_step_hz_last = 0;

        /* motion kết thúc -> cho comm log lại bình thường */
        Comm_SetMotionActive(false);
    }
}

void Motion_Task(void)
{
    if (motion_done_flag)
    {
        motion_done_flag = false;
        System_Log(LOG_INFO, "Motion done");
        System_NotifyMotionDone();
    }
}

void Motion_Stop_Immediately(void)
{
    /* Stop tracking velocity mode as well */
    if (s_track_active)
    {
        s_track_cmd_vx = s_track_cmd_vy = s_track_cmd_vz = 0.0f;
        s_track_cur_vx = s_track_cur_vy = s_track_cur_vz = 0.0f;
        s_track_phase_x = s_track_phase_y = s_track_phase_z = 0.0f;
        s_track_active = false;
        track_timer_stop();
    }

    motion_active = false;
    motion_done_flag = false;
    current_speed = 0.0f;
    enable_delay_ms = 0;

    HAL_TIM_Base_Stop_IT(&htim2);
    Driver_Disable_All();

    s_step_hz_last = 0;

    /* stop -> cho comm log lại bình thường */
    Comm_SetMotionActive(false);

    System_Log(LOG_WARN, "Motion emergency stop");
}

bool Motion_IsActive(void)
{
    return motion_active || (s_track_active && s_track_timer_running);
}

/* ================= TRACKING VELOCITY MODE API ================= */
void Motion_Track_SetVel(bool use_x, bool use_y, bool use_z, float vx, float vy, float vz)
{
    /* If any discrete move is active, reject (caller should schedule when idle) */
    if (motion_active) return;

    if (!s_track_active)
    {
        s_track_active = true;
        s_track_phase_x = s_track_phase_y = s_track_phase_z = 0.0f;
    }

    /* update watchdog timestamp */
    s_track_last_cmd_ms = HAL_GetTick();

    /* Per-axis clamp (safety). Keep symmetric caps (+/-). */
    if (use_x)
    {
        if (vx >  TVEL_CAP_X_MMPS) vx =  TVEL_CAP_X_MMPS;
        if (vx < -TVEL_CAP_X_MMPS) vx = -TVEL_CAP_X_MMPS;
    }
    if (use_y)
    {
        if (vy >  TVEL_CAP_Y_MMPS) vy =  TVEL_CAP_Y_MMPS;
        if (vy < -TVEL_CAP_Y_MMPS) vy = -TVEL_CAP_Y_MMPS;
    }
    if (use_z)
    {
        if (vz >  TVEL_CAP_Z_MMPS) vz =  TVEL_CAP_Z_MMPS;
        if (vz < -TVEL_CAP_Z_MMPS) vz = -TVEL_CAP_Z_MMPS;
    }

    s_track_cmd_vx = use_x ? vx : 0.0f;
    s_track_cmd_vy = use_y ? vy : 0.0f;
    s_track_cmd_vz = use_z ? vz : 0.0f;

    /* Start timer immediately if command non-zero */
    float av = f_max3(f_abs(s_track_cmd_vx), f_abs(s_track_cmd_vy), f_abs(s_track_cmd_vz));
    if (av > 0.05f)
    {
        track_timer_start();
    }
}

void Motion_Track_Stop(void)
{
    s_track_cmd_vx = s_track_cmd_vy = s_track_cmd_vz = 0.0f;
    s_track_cur_vx = s_track_cur_vy = s_track_cur_vz = 0.0f;
    s_track_phase_x = s_track_phase_y = s_track_phase_z = 0.0f;
    s_track_last_cmd_ms = HAL_GetTick();
    track_timer_stop();
    s_track_active = false;
}

bool Motion_Track_IsActive(void)
{
    return s_track_active;
}
