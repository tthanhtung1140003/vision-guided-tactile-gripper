#include "homing/homing.h"

#include "motion/motion.h"
#include "limit/limit.h"
#include "system/system.h"
#include "error/error.h"

#include "stm32f1xx_hal.h"

#define HOMING_TRAVEL_XY_MM     400.0f
#define HOMING_TRAVEL_Z_MM      200.0f

#define HOMING_BACKOFF_XY_MM      15.0f
#define HOMING_BACKOFF_Z_MM       15.0f

/* HOMING SPEED*/
#define HOMING_FAST_XY_MM_S     30.0f
#define HOMING_SLOW_XY_MM_S      10.0f

#define HOMING_FAST_Z_MM_S       40.0f
#define HOMING_SLOW_Z_MM_S        10.0f

#define HOMING_ACCEL_XY_MM_S2    150.0f
#define HOMING_ACCEL_Z_MM_S2     250.0f

/* TIMEOUTS */
#define HOMING_FAST_TIMEOUT_MS    30000U
#define HOMING_BACKOFF_TIMEOUT_MS  8000U
#define HOMING_SLOW_TIMEOUT_MS    40000U

typedef enum
{
    H_IDLE = 0,

    /* Z */
    H_Z_PRE_RELEASE,
    H_Z_FAST,
    H_Z_BACKOFF,
    H_Z_SLOW,

    /* Y */
    H_Y_PRE_RELEASE,
    H_Y_FAST,
    H_Y_BACKOFF,
    H_Y_SLOW,

    /* X */
    H_X_PRE_RELEASE,
    H_X_FAST,
    H_X_BACKOFF,
    H_X_SLOW,

    /* DONE/FAIL */
    H_DONE,
    H_FAIL
} homing_state_t;

static homing_state_t hs = H_IDLE;
static uint32_t hs_start_ms = 0;
static bool phase_started = false;

static inline uint32_t now_ms(void) { return HAL_GetTick(); }

static void enter_state(homing_state_t s)
{
    hs = s;
    hs_start_ms = now_ms();
    phase_started = false;
}

static bool timeout_ms(uint32_t ms)
{
    return (now_ms() - hs_start_ms) > ms;
}

/* move relative (dx,dy,dz) mm */
static void move_rel(bool use_x, bool use_y, bool use_z, float dx, float dy, float dz)
{
    float x, y, z;
    Motion_GetPosition(&x, &y, &z);

    if (use_x) x += dx;
    if (use_y) y += dy;
    if (use_z) z += dz;

    Motion_MoveTo(use_x, use_y, use_z, x, y, z);
}

void Homing_Init(void)
{
    hs = H_IDLE;
    phase_started = false;
    hs_start_ms = 0;
}

bool Homing_IsActive(void)
{
    return (hs != H_IDLE);
}

void Homing_Start(void)
{
    if (Motion_IsActive())
    {
        System_Log(LOG_WARN, "HOME blocked: motion active");
        return;
    }

    if (System_State_Get() == SYS_ERROR || System_State_Get() == SYS_STOPPED)
    {
        System_Log(LOG_WARN, "HOME blocked: system not ready");
        return;
    }

    System_State_Set(SYS_HOMING);
    Motion_SetHomed(false); /* NEW: reset homed flag at start */
    System_Log(LOG_INFO, "Homing start");
    enter_state(H_Z_PRE_RELEASE);
}

void Homing_Task(void)
{
    if (hs == H_IDLE) return;
    if (System_State_Get() != SYS_HOMING)
    {
        hs = H_IDLE;
        return;
    }

    switch (hs)
    {
        case H_Z_PRE_RELEASE:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_Z_MM_S2);

                if (Limit_Z_Min())
                {
                    Motion_SetSpeed(0, 0, HOMING_FAST_Z_MM_S);
                    move_rel(false, false, true, 0, 0, +HOMING_BACKOFF_Z_MM);
                    phase_started = true;
                    System_Log(LOG_INFO, "HOME Z: pre-release");
                }
                else
                {
                    enter_state(H_Z_FAST);
                }
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_SWITCH_STUCK);
                    enter_state(H_FAIL);
                }
                else if (!Limit_Z_Min() && !Motion_IsActive())
                {
                    enter_state(H_Z_FAST);
                }
            }
            break;

        case H_Z_FAST:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_Z_MM_S2);
                Motion_SetSpeed(0, 0, HOMING_FAST_Z_MM_S);

                move_rel(false, false, true, 0, 0, -HOMING_TRAVEL_Z_MM);
                phase_started = true;
                System_Log(LOG_INFO, "HOME Z: fast");
            }
            else
            {
                if (timeout_ms(HOMING_FAST_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_Z_Min())
                {
                    Motion_Stop_Immediately();
                    enter_state(H_Z_BACKOFF);
                }
            }
            break;

        case H_Z_BACKOFF:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_Z_MM_S2);
                Motion_SetSpeed(0, 0, HOMING_FAST_Z_MM_S);

                move_rel(false, false, true, 0, 0, +HOMING_BACKOFF_Z_MM);
                phase_started = true;
                System_Log(LOG_INFO, "HOME Z: backoff");
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (!Motion_IsActive())
                {
                    if (Limit_Z_Min())
                    {
                        Error_Set(ERR_HOMING_SWITCH_STUCK);
                        enter_state(H_FAIL);
                    }
                    else
                    {
                        enter_state(H_Z_SLOW);
                    }
                }
            }
            break;

        case H_Z_SLOW:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_Z_MM_S2);
                Motion_SetSpeed(0, 0, HOMING_SLOW_Z_MM_S);

                move_rel(false, false, true, 0, 0, -(HOMING_BACKOFF_Z_MM * 3.0f));
                phase_started = true;
                System_Log(LOG_INFO, "HOME Z: slow");
            }
            else
            {
                if (timeout_ms(HOMING_SLOW_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_Z_Min())
                {
                    Motion_Stop_Immediately();

                    /* set Z = 0 */
                    float x, y, z;
                    Motion_GetPosition(&x, &y, &z);
                    Motion_SetPosition(x, y, 0.0f);

                    enter_state(H_Y_PRE_RELEASE);
                }
            }
            break;

        /* ====================== Y ====================== */
        case H_Y_PRE_RELEASE:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);

                if (Limit_Y_Min())
                {
                    Motion_SetSpeed(0, HOMING_FAST_XY_MM_S, 0);
                    move_rel(false, true, false, 0, +HOMING_BACKOFF_XY_MM, 0);
                    phase_started = true;
                    System_Log(LOG_INFO, "HOME Y: pre-release");
                }
                else
                {
                    enter_state(H_Y_FAST);
                }
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_SWITCH_STUCK);
                    enter_state(H_FAIL);
                }
                else if (!Limit_Y_Min() && !Motion_IsActive())
                {
                    enter_state(H_Y_FAST);
                }
            }
            break;

        case H_Y_FAST:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(0, HOMING_FAST_XY_MM_S, 0);

                move_rel(false, true, false, 0, -HOMING_TRAVEL_XY_MM, 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME Y: fast");
            }
            else
            {
                if (timeout_ms(HOMING_FAST_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_Y_Min())
                {
                    Motion_Stop_Immediately();
                    enter_state(H_Y_BACKOFF);
                }
            }
            break;

        case H_Y_BACKOFF:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(0, HOMING_FAST_XY_MM_S, 0);

                move_rel(false, true, false, 0, +HOMING_BACKOFF_XY_MM, 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME Y: backoff");
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (!Motion_IsActive())
                {
                    if (Limit_Y_Min())
                    {
                        Error_Set(ERR_HOMING_SWITCH_STUCK);
                        enter_state(H_FAIL);
                    }
                    else
                    {
                        enter_state(H_Y_SLOW);
                    }
                }
            }
            break;

        case H_Y_SLOW:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(0, HOMING_SLOW_XY_MM_S, 0);

                move_rel(false, true, false, 0, -(HOMING_BACKOFF_XY_MM * 3.0f), 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME Y: slow");
            }
            else
            {
                if (timeout_ms(HOMING_SLOW_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_Y_Min())
                {
                    Motion_Stop_Immediately();

                    /* set Y = 0 */
                    float x, y, z;
                    Motion_GetPosition(&x, &y, &z);
                    Motion_SetPosition(x, 0.0f, z);

                    enter_state(H_X_PRE_RELEASE);
                }
            }
            break;

        /* ====================== X ====================== */
        case H_X_PRE_RELEASE:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);

                if (Limit_X_Min())
                {
                    Motion_SetSpeed(HOMING_FAST_XY_MM_S, 0, 0);
                    move_rel(true, false, false, +HOMING_BACKOFF_XY_MM, 0, 0);
                    phase_started = true;
                    System_Log(LOG_INFO, "HOME X: pre-release");
                }
                else
                {
                    enter_state(H_X_FAST);
                }
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_SWITCH_STUCK);
                    enter_state(H_FAIL);
                }
                else if (!Limit_X_Min() && !Motion_IsActive())
                {
                    enter_state(H_X_FAST);
                }
            }
            break;

        case H_X_FAST:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(HOMING_FAST_XY_MM_S, 0, 0);

                move_rel(true, false, false, -HOMING_TRAVEL_XY_MM, 0, 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME X: fast");
            }
            else
            {
                if (timeout_ms(HOMING_FAST_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_X_Min())
                {
                    Motion_Stop_Immediately();
                    enter_state(H_X_BACKOFF);
                }
            }
            break;

        case H_X_BACKOFF:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(HOMING_FAST_XY_MM_S, 0, 0);

                move_rel(true, false, false, +HOMING_BACKOFF_XY_MM, 0, 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME X: backoff");
            }
            else
            {
                if (timeout_ms(HOMING_BACKOFF_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (!Motion_IsActive())
                {
                    if (Limit_X_Min())
                    {
                        Error_Set(ERR_HOMING_SWITCH_STUCK);
                        enter_state(H_FAIL);
                    }
                    else
                    {
                        enter_state(H_X_SLOW);
                    }
                }
            }
            break;

        case H_X_SLOW:
            if (!phase_started)
            {
                Motion_SetAcceleration(HOMING_ACCEL_XY_MM_S2);
                Motion_SetSpeed(HOMING_SLOW_XY_MM_S, 0, 0);

                move_rel(true, false, false, -(HOMING_BACKOFF_XY_MM * 3.0f), 0, 0);
                phase_started = true;
                System_Log(LOG_INFO, "HOME X: slow");
            }
            else
            {
                if (timeout_ms(HOMING_SLOW_TIMEOUT_MS))
                {
                    Error_Set(ERR_HOMING_TIMEOUT);
                    enter_state(H_FAIL);
                }
                else if (Limit_X_Min())
                {
                    Motion_Stop_Immediately();

                    /* set X = 0 */
                    float x, y, z;
                    Motion_GetPosition(&x, &y, &z);
                    Motion_SetPosition(0.0f, y, z);

                    enter_state(H_DONE);
                }
            }
            break;

        /* ====================== DONE/FAIL ====================== */
        case H_DONE:
            Motion_SetHomed(true);
            System_State_Set(SYS_IDLE);
            System_Log(LOG_INFO, "Homing done");
            hs = H_IDLE;
            break;

        case H_FAIL:
        default:
            System_Log(LOG_ERROR, "Homing failed");
            hs = H_IDLE;
            break;
    }
}
