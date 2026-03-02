#include "system/system.h"
#include "comm/comm.h"
#include "error/error.h"
#include "motion/motion.h"

static system_state_t sys_state;
static uint32_t error_code = 0;

/* ===== internal helper ===== */
static inline bool system_motion_sensitive(void)
{
    /* Có thể dùng cả sys_state và Motion_IsActive để chắc chắn */
    if (Motion_IsActive()) return true;

    return (sys_state == SYS_MOVING ||
            sys_state == SYS_JOGGING ||
            sys_state == SYS_HOMING);
}

/* ===== LOG ===== */
void System_Log(log_level_t level, const char *msg)
{
    /*
     * Khi đang chạy, hạn chế log để tránh tải UART gây jitter:
     * - chỉ cho ERROR
     */
    if (system_motion_sensitive())
    {
        if (level != LOG_ERROR) return;
    }

    Comm_SendLog((uint8_t)level, msg);
}

/* ===== INIT ===== */
void System_State_Init(void)
{
    sys_state = SYS_IDLE;
    error_code = 0;
}

void System_State_Set(system_state_t state)
{
    sys_state = state;
}

system_state_t System_State_Get(void)
{
    return sys_state;
}

/* ===== STATE HELPERS ===== */
bool System_IsBusy(void)
{
    /* Nếu đang ERROR/STOPPED thì coi như busy theo nghĩa không nhận MOVE */
    if (sys_state == SYS_ERROR || sys_state == SYS_STOPPED) {
        return true;
    }

    if (sys_state == SYS_MOVING || sys_state == SYS_JOGGING)
    {
        if (!Motion_IsActive())
        {
            sys_state = SYS_IDLE;
            return false;
        }
        return true;
    }

    return (sys_state == SYS_HOMING);
}

void System_Acknowledge(void)
{
    Error_Clear();
    error_code = 0;
    sys_state = SYS_IDLE;

    /* Không cần spam INFO liên tục; để WARN/ERROR thôi */
    System_Log(LOG_INFO, "ACK: system to IDLE (errors cleared)");
}

void System_Stop(void)
{
    system_state_t prev = sys_state;

    Motion_Stop_Immediately();

    /* Nếu đang ERROR thì giữ ERROR */
    if (prev == SYS_ERROR) {
        System_Log(LOG_WARN, "STOP while ERROR: keep SYS_ERROR");
        return;
    }

    sys_state = SYS_STOPPED;
    System_Log(LOG_WARN, "System stopped");
}

void System_SetError(uint32_t err)
{
    error_code = err;
    sys_state = SYS_ERROR;
}

void System_NotifyMotionDone(void)
{
    system_state_t st = System_State_Get();
    if (st == SYS_MOVING || st == SYS_JOGGING)
    {
        System_State_Set(SYS_IDLE);
    }
}

void System_Task(void)
{
    /* currently empty */
}
