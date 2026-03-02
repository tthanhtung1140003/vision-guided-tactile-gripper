#ifndef COMM_H
#define COMM_H

#include <stdint.h>
#include <stdbool.h>

void Comm_Init(void);

/* flush TX */
void Comm_Task(void);
void Comm_SendLog(uint8_t level, const char *msg);

/* Notify comm layer that motion is active (to reduce logs / rate limit) */
void Comm_SetMotionActive(bool active);

/* HAL_UART_TxCpltCallback (ISR) */
void Comm_OnTxCpltISR(void);

#endif /* COMM_H */
