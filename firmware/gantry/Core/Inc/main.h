#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f1xx_hal.h"

/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
/* USER CODE END Includes */

extern uint8_t uart_rx_byte;

void Error_Handler(void);

/* Private defines -----------------------------------------------------------*/
#define X_step_Pin GPIO_PIN_0
#define X_step_GPIO_Port GPIOA
#define X_dir_Pin GPIO_PIN_1
#define X_dir_GPIO_Port GPIOA
#define Y_step_Pin GPIO_PIN_3
#define Y_step_GPIO_Port GPIOA
#define Y_dir_Pin GPIO_PIN_4
#define Y_dir_GPIO_Port GPIOA
#define Z_step_Pin GPIO_PIN_6
#define Z_step_GPIO_Port GPIOA
#define Z_dir_Pin GPIO_PIN_7
#define Z_dir_GPIO_Port GPIOA

#define X_min_Pin GPIO_PIN_0
#define X_min_GPIO_Port GPIOB
#define X_max_Pin GPIO_PIN_1
#define X_max_GPIO_Port GPIOB
#define Y_min_Pin GPIO_PIN_10
#define Y_min_GPIO_Port GPIOB
#define Y_max_Pin GPIO_PIN_11
#define Y_max_GPIO_Port GPIOB
#define Z_min_Pin GPIO_PIN_12
#define Z_min_GPIO_Port GPIOB
#define Z_max_Pin GPIO_PIN_13
#define Z_max_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* Map chuẩn cho driver STEP/DIR */
#define STEP_X_Pin        X_step_Pin
#define STEP_X_GPIO_Port  X_step_GPIO_Port
#define DIR_X_Pin         X_dir_Pin
#define DIR_X_GPIO_Port   X_dir_GPIO_Port

#define STEP_Y_Pin        Y_step_Pin
#define STEP_Y_GPIO_Port  Y_step_GPIO_Port
#define DIR_Y_Pin         Y_dir_Pin
#define DIR_Y_GPIO_Port   Y_dir_GPIO_Port

#define STEP_Z_Pin        Z_step_Pin
#define STEP_Z_GPIO_Port  Z_step_GPIO_Port
#define DIR_Z_Pin         Z_dir_Pin
#define DIR_Z_GPIO_Port   Z_dir_GPIO_Port

/* ===== Optional ENA pins =====
   Nếu bạn có nối chân EN/ENA của driver về MCU:
   - Hãy tạo pin trong CubeMX và đặt tên lần lượt: X_ena, Y_ena, Z_ena
   - CubeMX sẽ sinh ra X_ena_Pin/X_ena_GPIO_Port...
   Nếu bạn KHÔNG có ENA -> các macro DRIVER_HAS_ENA_* = 0 và driver.c sẽ bỏ qua enable.
*/
#if defined(X_ena_Pin) && defined(X_ena_GPIO_Port)
  #define ENA_X_Pin       X_ena_Pin
  #define ENA_X_GPIO_Port X_ena_GPIO_Port
  #define DRIVER_HAS_ENA_X 1
#else
  #define DRIVER_HAS_ENA_X 0
#endif

#if defined(Y_ena_Pin) && defined(Y_ena_GPIO_Port)
  #define ENA_Y_Pin       Y_ena_Pin
  #define ENA_Y_GPIO_Port Y_ena_GPIO_Port
  #define DRIVER_HAS_ENA_Y 1
#else
  #define DRIVER_HAS_ENA_Y 0
#endif

#if defined(Z_ena_Pin) && defined(Z_ena_GPIO_Port)
  #define ENA_Z_Pin       Z_ena_Pin
  #define ENA_Z_GPIO_Port Z_ena_GPIO_Port
  #define DRIVER_HAS_ENA_Z 1
#else
  #define DRIVER_HAS_ENA_Z 0
#endif

/* Limit mapping */
#define X_MIN_Pin         X_min_Pin
#define X_MIN_GPIO_Port   X_min_GPIO_Port
#define X_MAX_Pin         X_max_Pin
#define X_MAX_GPIO_Port   X_max_GPIO_Port
#define Y_MIN_Pin         Y_min_Pin
#define Y_MIN_GPIO_Port   Y_min_GPIO_Port
#define Y_MAX_Pin         Y_max_Pin
#define Y_MAX_GPIO_Port   Y_max_GPIO_Port
#define Z_MIN_Pin         Z_min_Pin
#define Z_MIN_GPIO_Port   Z_min_GPIO_Port
#define Z_MAX_Pin         Z_max_Pin
#define Z_MAX_GPIO_Port   Z_max_GPIO_Port

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
