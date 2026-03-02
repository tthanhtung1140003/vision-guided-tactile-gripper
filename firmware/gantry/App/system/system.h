#ifndef SYSTEM_H
#define SYSTEM_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    SYS_STARTUP = 0,
    SYS_IDLE,
    SYS_JOGGING,
    SYS_MOVING,
    SYS_HOMING,
    SYS_STOPPED,
    SYS_ERROR
} system_state_t;

typedef enum {
    LOG_INFO = 0,
    LOG_WARN,
    LOG_ERROR
} log_level_t;

/* ===== LOG ===== */
void System_Log(log_level_t level, const char *msg);

void System_State_Init(void);
void System_State_Set(system_state_t state);
system_state_t System_State_Get(void);
void System_Task(void);
/* ===== NEW INTERNAL ===== */
void System_Acknowledge(void);
bool System_IsBusy(void);
void System_Stop(void);
void System_SetError(uint32_t err);
void System_NotifyMotionDone(void);

#endif
