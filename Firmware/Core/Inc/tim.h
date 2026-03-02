#ifndef __TIM_H__
#define __TIM_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

extern TIM_HandleTypeDef htim2;

void MX_TIM2_Init(void);

/* Helper: set frequency of TIM2 update interrupt (Hz) */
void TIM2_Set_Frequency(uint32_t hz);

#ifdef __cplusplus
}
#endif

#endif /* __TIM_H__ */
