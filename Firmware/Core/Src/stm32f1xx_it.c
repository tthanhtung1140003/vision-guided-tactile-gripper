#include "main.h"
#include "stm32f1xx_it.h"

#include "serial_rx.h"
#include "motion/motion.h"
#include "limit/limit.h"
#include "comm/comm.h"

#include "tick_1ms.h"

extern TIM_HandleTypeDef htim2;
extern UART_HandleTypeDef huart1;
extern uint8_t uart_rx_byte;

void NMI_Handler(void) { while (1) {} }
void HardFault_Handler(void) { while (1) {} }
void MemManage_Handler(void) { while (1) {} }
void BusFault_Handler(void) { while (1) {} }
void UsageFault_Handler(void) { while (1) {} }
void DebugMon_Handler(void) {}

void SysTick_Handler(void)
{
    HAL_IncTick();

    // ✅ SysTick ISR phải nhẹ: chỉ tăng tick pending
    Tick1ms_ISR();
}

void TIM2_IRQHandler(void)
{
    HAL_TIM_IRQHandler(&htim2);
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2)
    {
        Motion_Step_ISR();
    }
}

void USART1_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart1);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        SerialRx_Char((char)uart_rx_byte);
        HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1);
    }
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        Comm_OnTxCpltISR();
    }
}
