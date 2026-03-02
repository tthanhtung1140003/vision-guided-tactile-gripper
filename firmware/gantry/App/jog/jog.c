#include "jog/jog.h"
#include "motion/motion.h"
#include "system/system.h"
#include "limit/limit.h"

/* ================= CONFIG ================= */
static float jog_step_mm = 1.0f;

#define JOG_MAX_SPEED_X     60.0f   // mm/s
#define JOG_MAX_SPEED_Y    150.0f
#define JOG_MAX_SPEED_Z     15.0f

/* ================= INIT ================= */
void Jog_Init(void)
{
    jog_step_mm = 1.0f;
}

/* ================= CONFIG ================= */
void Jog_SetStep(float step_mm)
{
    if (step_mm < 0.01f) step_mm = 0.01f;
    jog_step_mm = step_mm;
}

/* ================= EXEC ================= */
void Jog_Execute(jog_dir_t dir)
{
    if (System_State_Get() == SYS_ERROR) return;
    if (System_IsBusy()) return;

    float x, y, z;
    Motion_GetPosition(&x, &y, &z);

    /* Lưu speed setting hiện tại (Motion_SetSpeed lấy max(|vx|,|vy|,|vz|)) */
    float prev_speed = Motion_GetSpeedSetting();

    /* Mặc định: không chạy */
    bool will_move = false;

    /* Target và speed theo trục jog */
    float tx = x, ty = y, tz = z;
    float sx = 0.0f, sy = 0.0f, sz = 0.0f;

    /* Hard-limit gating (tránh gọi Motion_MoveTo nếu đang chạm công tắc) */
    switch (dir)
    {
        case JOG_X_POS:
            if (Limit_X_Max()) { System_Log(LOG_WARN, "JOG blocked: X MAX"); goto cleanup; }
            tx = x + jog_step_mm;
            sx = JOG_MAX_SPEED_X;
            will_move = true;
            break;

        case JOG_X_NEG:
            if (Limit_X_Min()) { System_Log(LOG_WARN, "JOG blocked: X MIN"); goto cleanup; }
            tx = x - jog_step_mm;
            sx = JOG_MAX_SPEED_X;
            will_move = true;
            break;

        case JOG_Y_POS:
            if (Limit_Y_Max()) { System_Log(LOG_WARN, "JOG blocked: Y MAX"); goto cleanup; }
            ty = y + jog_step_mm;
            sy = JOG_MAX_SPEED_Y;
            will_move = true;
            break;

        case JOG_Y_NEG:
            if (Limit_Y_Min()) { System_Log(LOG_WARN, "JOG blocked: Y MIN"); goto cleanup; }
            ty = y - jog_step_mm;
            sy = JOG_MAX_SPEED_Y;
            will_move = true;
            break;

        case JOG_Z_POS:
            if (Limit_Z_Max()) { System_Log(LOG_WARN, "JOG blocked: Z MAX"); goto cleanup; }
            tz = z + jog_step_mm;
            sz = JOG_MAX_SPEED_Z;
            will_move = true;
            break;

        case JOG_Z_NEG:
            if (Limit_Z_Min()) { System_Log(LOG_WARN, "JOG blocked: Z MIN"); goto cleanup; }
            tz = z - jog_step_mm;
            sz = JOG_MAX_SPEED_Z;
            will_move = true;
            break;

        default:
            goto cleanup;
    }

    if (!will_move) goto cleanup;

    /* Set state + speed trước khi bắt đầu move */
    System_State_Set(SYS_JOGGING);
    Motion_SetSpeed(sx, sy, sz);

    /* Motion_MoveTo sẽ tự check soft limits (nếu đã homed và enable) */
    Motion_MoveTo(true, true, true, tx, ty, tz);

cleanup:
    /* Restore speed setting cho các lệnh sau (không ảnh hưởng job đang chạy vì Motion_MoveTo chốt s_job_target_speed) */
    Motion_SetSpeed(prev_speed, 0.0f, 0.0f);

    /* Nếu không có motion active thì trả state về IDLE (tránh kẹt SYS_JOGGING khi bị chặn) */
    if (!Motion_IsActive())
    {
        if (System_State_Get() == SYS_JOGGING)
            System_State_Set(SYS_IDLE);
    }
}
