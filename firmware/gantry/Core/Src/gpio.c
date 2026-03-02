#include "gpio.h"
#include "main.h"

void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();

  /* =========================
     Set initial output levels
     ========================= */
  /* STEP idle LOW (phù hợp kiểu pulse HIGH->LOW) */
  HAL_GPIO_WritePin(STEP_X_GPIO_Port, STEP_X_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(DIR_X_GPIO_Port,  DIR_X_Pin,  GPIO_PIN_RESET);

  HAL_GPIO_WritePin(STEP_Y_GPIO_Port, STEP_Y_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(DIR_Y_GPIO_Port,  DIR_Y_Pin,  GPIO_PIN_RESET);

  HAL_GPIO_WritePin(STEP_Z_GPIO_Port, STEP_Z_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(DIR_Z_GPIO_Port,  DIR_Z_Pin,  GPIO_PIN_RESET);

  /* =========================
     STEP / DIR outputs (X,Y,Z)
     ========================= */
  GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull  = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;

  /* X */
  GPIO_InitStruct.Pin = STEP_X_Pin | DIR_X_Pin;
  HAL_GPIO_Init(STEP_X_GPIO_Port, &GPIO_InitStruct);
  /* Y */
  GPIO_InitStruct.Pin = STEP_Y_Pin | DIR_Y_Pin;
  HAL_GPIO_Init(STEP_Y_GPIO_Port, &GPIO_InitStruct);

  /* Z */
  GPIO_InitStruct.Pin = STEP_Z_Pin | DIR_Z_Pin;
  HAL_GPIO_Init(STEP_Z_GPIO_Port, &GPIO_InitStruct);

  /* =========================
     LIMIT inputs (pull-up)
     ========================= */
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;

  /* X limits */
  GPIO_InitStruct.Pin = X_MIN_Pin | X_MAX_Pin;
  HAL_GPIO_Init(X_MIN_GPIO_Port, &GPIO_InitStruct);

  /* Y limits */
  GPIO_InitStruct.Pin = Y_MIN_Pin | Y_MAX_Pin;
  HAL_GPIO_Init(Y_MIN_GPIO_Port, &GPIO_InitStruct);

  /* Z limits */
  GPIO_InitStruct.Pin = Z_MIN_Pin | Z_MAX_Pin;
  HAL_GPIO_Init(Z_MIN_GPIO_Port, &GPIO_InitStruct);
}
