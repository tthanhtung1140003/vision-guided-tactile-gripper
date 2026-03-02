#ifndef SERIAL_RX_H
#define SERIAL_RX_H

#include <stdbool.h>

void SerialRx_Init(void);
void SerialRx_Char(char c);

void SerialRx_Tick_1ms(void);

bool SerialRx_LineReady(void);
void SerialRx_GetLine(char *out);

#endif
