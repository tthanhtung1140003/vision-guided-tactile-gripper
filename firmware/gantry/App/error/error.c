#include "error/error.h"
#include "system/system.h"

volatile error_t sys_error = ERR_NONE;

void Error_Set(error_t err)
{
    sys_error = err;
    System_SetError((uint32_t)err);

    switch (err) {
        case ERR_LIMIT:
            System_Log(LOG_ERROR, "Limit triggered");
            break;
        case ERR_ESTOP:
            System_Log(LOG_ERROR, "Emergency stop");
            break;
        case ERR_RX_OVERFLOW:
            System_Log(LOG_ERROR, "Serial RX overflow");
            break;
        case ERR_HOMING_TIMEOUT:
            System_Log(LOG_ERROR, "Homing timeout");
            break;
        case ERR_HOMING_SWITCH_STUCK:
            System_Log(LOG_ERROR, "Homing switch stuck");
            break;
        default:
            System_Log(LOG_ERROR, "Unknown error");
            break;
    }
}

void Error_Clear(void)
{
    sys_error = ERR_NONE;
    if (System_State_Get() == SYS_ERROR)
        System_State_Set(SYS_IDLE);
}
