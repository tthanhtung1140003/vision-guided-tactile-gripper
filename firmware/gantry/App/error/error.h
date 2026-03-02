#ifndef ERROR_H
#define ERROR_H

#include "stdint.h"

typedef enum {
    ERR_NONE = 0,
    ERR_LIMIT,
    ERR_ESTOP,
    ERR_RX_OVERFLOW,
    ERR_HOMING_TIMEOUT,
    ERR_HOMING_SWITCH_STUCK,
    ERR_UNKNOWN
} error_t;

/* error system */
extern volatile error_t sys_error;

/* API */
void Error_Set(error_t err);
void Error_Clear(void);

#endif /* ERROR_H */
