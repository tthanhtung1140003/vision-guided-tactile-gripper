#include "limit/limit.h"
#include "main.h"
#include "system/system.h"
#include "motion/motion.h"
#include "error/error.h"
#include "driver/driver.h"
#include "stm32f1xx_hal.h"

#define READ_LIMIT(port, pin) (HAL_GPIO_ReadPin((port), (pin)) == LIMIT_ACTIVE_STATE)

/* ===== SINGLE AXIS LIMIT READ ===== */
bool Limit_X_Min(void) { return READ_LIMIT(X_min_GPIO_Port, X_min_Pin); }
bool Limit_X_Max(void) { return READ_LIMIT(X_max_GPIO_Port, X_max_Pin); }
bool Limit_Y_Min(void) { return READ_LIMIT(Y_min_GPIO_Port, Y_min_Pin); }
bool Limit_Y_Max(void) { return READ_LIMIT(Y_max_GPIO_Port, Y_max_Pin); }
bool Limit_Z_Min(void) { return READ_LIMIT(Z_min_GPIO_Port, Z_min_Pin); }
bool Limit_Z_Max(void) { return READ_LIMIT(Z_max_GPIO_Port, Z_max_Pin); }

void Limit_Init(void) {}

/* Check directional limit per-axis (the one in the moving direction only) */
static inline bool limit_hit_dir(axis_t axis)
{
    switch (axis)
    {
        case AXIS_X:
            return Driver_IsDirPositive(AXIS_X) ? Limit_X_Max() : Limit_X_Min();
        case AXIS_Y:
            return Driver_IsDirPositive(AXIS_Y) ? Limit_Y_Max() : Limit_Y_Min();
        case AXIS_Z:
            return Driver_IsDirPositive(AXIS_Z) ? Limit_Z_Max() : Limit_Z_Min();
        default:
            return false;
    }
}

static inline bool any_limit_directional(void)
{
    /* Chỉ check 3 lần, mỗi lần đúng 1 switch theo hướng */
    if (limit_hit_dir(AXIS_X)) return true;
    if (limit_hit_dir(AXIS_Y)) return true;
    if (limit_hit_dir(AXIS_Z)) return true;
    return false;
}

/* ===== HARD LIMIT ===== */
void Limit_Hard_Check(void)
{
    /* Robust hard-limit debounce to avoid EMI / bounce in real hardware.
     * - Per-axis debounce (integrator)
     * - Direction-change blanking window (ignore limit briefly after dir flip)
     * Called at 1ms rate from main loop.
     */
    enum { DEBOUNCE_MS = 100, BLANK_MS = 40 };

    static uint16_t hit_ms[3] = {0, 0, 0};
    static int8_t   last_dir[3] = {0, 0, 0};      /* +1 / -1 */
    static uint16_t blank_ms[3] = {0, 0, 0};
    static bool latched = false;

    system_state_t st = System_State_Get();

    if (st != SYS_MOVING && st != SYS_JOGGING)
    {
        hit_ms[0] = hit_ms[1] = hit_ms[2] = 0;
        blank_ms[0] = blank_ms[1] = blank_ms[2] = 0;
        latched = false;
        return;
    }

    if (latched) return;

    if (sys_error != ERR_NONE)
    {
        hit_ms[0] = hit_ms[1] = hit_ms[2] = 0;
        latched = true;
        return;
    }

    /* Update blanking on direction changes */
    for (int a = 0; a < 3; a++)
    {
        int8_t dir = Driver_IsDirPositive((axis_t)a) ? +1 : -1;
        if (last_dir[a] == 0) last_dir[a] = dir;
        if (dir != last_dir[a])
        {
            last_dir[a] = dir;
            blank_ms[a] = BLANK_MS;
            hit_ms[a] = 0;
        }
        else
        {
            if (blank_ms[a] > 0) blank_ms[a]--;
        }
    }

    bool trig = false;

    for (int a = 0; a < 3; a++)
    {
        if (blank_ms[a] > 0)
        {
            hit_ms[a] = 0;
            continue;
        }

        bool hit = limit_hit_dir((axis_t)a);
        if (hit)
        {
            if (hit_ms[a] < DEBOUNCE_MS) hit_ms[a]++;
            if (hit_ms[a] >= DEBOUNCE_MS)
            {
                trig = true;
                break;
            }
        }
        else
        {
            hit_ms[a] = 0;
        }
    }

    if (trig)
    {
        latched = true;
        Error_Set(ERR_LIMIT);
        Motion_Stop_Immediately();
    }
}
