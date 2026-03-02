#include "tick_1ms.h"
#include "stm32f1xx.h"

static volatile uint32_t s_tick1ms_pending = 0;

void Tick1ms_Init(void)
{
    s_tick1ms_pending = 0;
}

void Tick1ms_ISR(void)
{
    // tối giản, chỉ tăng counter
    s_tick1ms_pending++;
}

uint32_t Tick1ms_Pop(void)
{
    uint32_t n;
    __disable_irq();
    n = s_tick1ms_pending;
    s_tick1ms_pending = 0;
    __enable_irq();
    return n;
}
