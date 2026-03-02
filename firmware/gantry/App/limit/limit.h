#ifndef LIMIT_H
#define LIMIT_H

#include <stdbool.h>
#include "stm32f1xx_hal.h"

/* NO to GND with pull-up: pressed = LOW */
#define LIMIT_ACTIVE_STATE GPIO_PIN_RESET

void Limit_Init(void);

bool Limit_X_Min(void);
bool Limit_X_Max(void);
bool Limit_Y_Min(void);
bool Limit_Y_Max(void);
bool Limit_Z_Min(void);
bool Limit_Z_Max(void);

/* called from SysTick 1ms */
void Limit_Hard_Check(void);

#endif
