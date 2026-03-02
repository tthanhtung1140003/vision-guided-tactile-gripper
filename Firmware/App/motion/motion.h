#ifndef MOTION_H
#define MOTION_H

#include <stdbool.h>

void Motion_Init(void);
void Motion_SetSpeed(float vx, float vy, float vz);
float Motion_GetSpeedSetting(void);
void Motion_SetAcceleration(float accel_mm_s2);
void Motion_SetPosition(float x, float y, float z);
void Motion_GetPosition(float *x, float *y, float *z);
void Motion_GetAxisSpeeds(float *vx, float *vy, float *vz);
void Motion_MoveTo(bool use_x, bool use_y, bool use_z, float x, float y, float z);
void Motion_Task(void);
void Motion_Tick_1ms(void);
void Motion_Step_ISR(void);
void Motion_Stop_Immediately(void);
bool Motion_IsActive(void);

/* ===== Smooth tracking: velocity mode (TVEL) =====
 * GUI can send: TVEL X+40.0 Y0.0 Z-20.0
 * Continuous motion with accel limiting + watchdog.
 */
void Motion_Track_SetVel(bool use_x, bool use_y, bool use_z, float vx, float vy, float vz);
void Motion_Track_Stop(void);
bool Motion_Track_IsActive(void);

void Motion_SetHomed(bool homed);
bool Motion_IsHomed(void);
void Motion_EnableSoftLimits(bool enable);

#endif /* MOTION_H */
