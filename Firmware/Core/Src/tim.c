#include "tim.h"
#include "stm32f1xx_hal.h"

/* TIM2 handle */
TIM_HandleTypeDef htim2;

static uint32_t tim2_get_clock_hz(void)
{
    uint32_t pclk1 = HAL_RCC_GetPCLK1Freq();

    uint32_t cfgr = RCC->CFGR;
    uint32_t ppre1 = (cfgr >> RCC_CFGR_PPRE1_Pos) & 0x7;

    if (ppre1 < 4) return pclk1;
    return pclk1 * 2;
}

static uint32_t tim2_get_tick_hz_1mhz(uint16_t *out_psc)
{
    uint32_t timclk = tim2_get_clock_hz();

    uint32_t presc = (timclk / 1000000UL);
    if (presc < 1) presc = 1;

    if (out_psc) *out_psc = (uint16_t)(presc - 1u);
    return timclk / presc;
}

void MX_TIM2_Init(void)
{
    __HAL_RCC_TIM2_CLK_ENABLE();

    htim2.Instance = TIM2;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;

    /* Enable ARR preload để update ARR không tạo chu kỳ dị */
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;

    uint16_t psc = 0;
    uint32_t tick_hz = tim2_get_tick_hz_1mhz(&psc);
    htim2.Init.Prescaler = psc;

    uint32_t arr = (tick_hz / 1000UL);
    if (arr < 2u) arr = 2u;
    if (arr > 0xFFFFu) arr = 0xFFFFu;
    htim2.Init.Period = (uint16_t)(arr - 1u);

    if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_NVIC_SetPriority(TIM2_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);

    __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
    __HAL_TIM_SET_COUNTER(&htim2, 0u);
}

/* Set update interrupt frequency (Hz) */
void TIM2_Set_Frequency(uint32_t hz)
{
    if (hz < 1u) hz = 1u;
    if (hz > 200000u) hz = 200000u;

    uint16_t desired_psc = 0;
    uint32_t tick_hz = tim2_get_tick_hz_1mhz(&desired_psc);

    uint32_t arr = (tick_hz / hz);
    if (arr < 2u) arr = 2u;
    if (arr > 0xFFFFu) arr = 0xFFFFu;
    uint16_t new_arr = (uint16_t)(arr - 1u);

    /* Nếu không đổi thì thôi */
    if (__HAL_TIM_GET_AUTORELOAD(&htim2) == new_arr)
        return;

    uint32_t was_enabled = (htim2.Instance->CR1 & TIM_CR1_CEN);

    __HAL_TIM_DISABLE(&htim2);

    /* PSC trên F1 đọc/ghi trực tiếp PSC (không có __HAL_TIM_GET_PRESCALER) */
    uint16_t cur_psc = (uint16_t)(htim2.Instance->PSC);
    if (cur_psc != desired_psc)
    {
        __HAL_TIM_SET_PRESCALER(&htim2, desired_psc);
    }

    __HAL_TIM_SET_AUTORELOAD(&htim2, new_arr);
    __HAL_TIM_SET_COUNTER(&htim2, 0u);

    /* Force update event to load ARR/PSC ngay lập tức */
    htim2.Instance->EGR = TIM_EGR_UG;

    __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);

    if (was_enabled)
    {
        __HAL_TIM_ENABLE(&htim2);
    }
}
