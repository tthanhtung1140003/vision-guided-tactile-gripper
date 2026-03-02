#ifndef DRIVER_H
#define DRIVER_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    AXIS_X = 0,
    AXIS_Y = 1,
    AXIS_Z = 2
} axis_t;

/* STEP/DIR */
void Driver_Enable_All(void);
void Driver_Disable_All(void);

void Driver_SetDir(axis_t axis, uint8_t dir_positive);
uint8_t Driver_IsDirPositive(axis_t axis);

void Driver_Step_Axis(axis_t axis);

#endif /* DRIVER_H */
