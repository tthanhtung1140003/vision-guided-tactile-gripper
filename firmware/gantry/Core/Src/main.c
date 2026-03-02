#include "main.h"
#include "serial_rx.h"
#include "gpio.h"

#include "tick_1ms.h"

/* ================= USER MODULES ================= */
#include "protocol/protocol.h"
#include "motion/motion.h"
#include "limit/limit.h"
#include "homing/homing.h"
#include "jog/jog.h"
#include "comm/comm.h"
#include "system/system.h"

/* ================= CubeMX ================= */
#include "tim.h"
#include "usart.h"

/* ================= PROTOTYPES ================= */
void SystemClock_Config(void);
void Error_Handler(void);

/* ===== UART RX ===== */
uint8_t uart_rx_byte;

/* ================= MAIN ================= */
int main(void)
{
    HAL_Init();

    /* SysTick priority (bạn đã làm bước 1; giữ lại ở đây ok) */
    HAL_NVIC_SetPriority(SysTick_IRQn, 3, 0);

    /* ✅ init tick_1ms counter */
    Tick1ms_Init();

    SystemClock_Config();

    /* ===== CubeMX peripherals ===== */
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_TIM2_Init();

    /* ===== UART RX ===== */
    SerialRx_Init();
    HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1);

    /* ===== App init ===== */
    System_State_Init();
    Comm_Init();
    Protocol_Init();
    Motion_Init();
    Limit_Init();
    Jog_Init();

    /* ===== BOOT LOG ===== */
    HAL_Delay(300);
    System_Log(LOG_INFO, "System boot");

    /* ================= MAIN LOOP ================= */
    while (1)
    {
        /* ✅ xử lý tick 1ms ở MAIN (không làm trong SysTick ISR nữa) */
        uint32_t n1ms = Tick1ms_Pop();
        while (n1ms--)
        {
            SerialRx_Tick_1ms();
            Motion_Tick_1ms();
            Limit_Hard_Check();
        }

        /* Flush UART TX (non-blocking logger). */
        Comm_Task();

        Protocol_Task();
        Motion_Task();
        System_Task();

        if (System_State_Get() == SYS_HOMING)
        {
            Homing_Task();
        }
    }
}

/* ================= CLOCK ================= */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType =
        RCC_CLOCKTYPE_HCLK |
        RCC_CLOCKTYPE_SYSCLK |
        RCC_CLOCKTYPE_PCLK1 |
        RCC_CLOCKTYPE_PCLK2;

    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
    {
        Error_Handler();
    }
}

/* ================= ERROR HANDLER ================= */
void Error_Handler(void)
{
    __disable_irq();
    while (1)
    {
    }
}
