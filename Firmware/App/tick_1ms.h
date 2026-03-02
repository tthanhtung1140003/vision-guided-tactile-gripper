#pragma once
#include <stdint.h>

/**
 * Tick1ms được set trong SysTick ISR.
 * Main loop gọi Tick1ms_Pop() để lấy số tick pending.
 */
void Tick1ms_Init(void);
void Tick1ms_ISR(void);
uint32_t Tick1ms_Pop(void);
