/**
 * @file    serial_rx.c
 * @brief   UART RX line receiver (ISR feed + 1ms idle timeout).
 *
 * Design goals:
 *  - ISR cực nhẹ: chỉ append byte, gặp newline/timeout thì "chốt line" bằng flag.
 *  - KHÔNG strncpy/memcpy trong ISR, KHÔNG __disable_irq dài trong ISR.
 *  - Khi line_ready=1, ISR bỏ qua mọi byte đến khi main lấy line.
 *
 * API must match serial_rx.h:
 *   void SerialRx_Init(void);
 *   void SerialRx_Char(char c);
 *   void SerialRx_Tick_1ms(void);
 *   bool SerialRx_LineReady(void);
 *   void SerialRx_GetLine(char *out);
 */

#include "serial_rx.h"
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

// For __disable_irq / __enable_irq / __get_PRIMASK
#include "stm32f1xx.h"   // (CMSIS core + device header used by STM32F1)

/* =========================
 * Config
 * ========================= */
#ifndef SERIAL_RX_BUF_SIZE
#define SERIAL_RX_BUF_SIZE            64u
#endif

#ifndef SERIAL_RX_IDLE_TIMEOUT_MS
#define SERIAL_RX_IDLE_TIMEOUT_MS     30u
#endif

#ifndef SERIAL_RX_LINE_QUEUE_LEN
#define SERIAL_RX_LINE_QUEUE_LEN      8u   /* number of full lines buffered */
#endif

#include "serial_rx.h"
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

// For __disable_irq / __enable_irq / __get_PRIMASK
#include "stm32f1xx.h"

/* =========================
 * Internal state (shared ISR <-> main)
 * ========================= */
static volatile uint16_t s_build_idx = 0;
static volatile uint16_t s_idle_ms   = 0;

/* line queue */
static char s_lines[SERIAL_RX_LINE_QUEUE_LEN][SERIAL_RX_BUF_SIZE];
static volatile uint8_t s_q_head = 0;
static volatile uint8_t s_q_tail = 0;
static volatile uint8_t s_q_count = 0;

static volatile bool s_drop_until_eol = false;

static inline uint8_t q_next(uint8_t v)
{
    return (uint8_t)((v + 1u) % SERIAL_RX_LINE_QUEUE_LEN);
}

static inline void finalize_line_isr(void)
{
    if (s_build_idx == 0u) return; // ignore empty
    if (s_q_count >= SERIAL_RX_LINE_QUEUE_LEN) {
        // queue full -> drop until EOL
        s_drop_until_eol = true;
        s_build_idx = 0u;
        return;
    }

    // Null terminate safely inside current tail slot
    if (s_build_idx >= (SERIAL_RX_BUF_SIZE - 1u)) {
        s_lines[s_q_tail][SERIAL_RX_BUF_SIZE - 1u] = '\0';
    } else {
        s_lines[s_q_tail][s_build_idx] = '\0';
    }

    // commit
    s_q_tail = q_next(s_q_tail);
    s_q_count++;

    // reset builder
    s_build_idx = 0u;
}

/* =========================
 * Public API
 * ========================= */
void SerialRx_Init(void)
{
    uint32_t prim = __get_PRIMASK();
    __disable_irq();

    s_build_idx = 0u;
    s_idle_ms   = 0u;
    s_q_head = s_q_tail = 0u;
    s_q_count = 0u;
    s_drop_until_eol = false;

    for (uint32_t i = 0; i < SERIAL_RX_LINE_QUEUE_LEN; i++) {
        memset(s_lines[i], 0, SERIAL_RX_BUF_SIZE);
    }

    if (!prim) __enable_irq();
}

void SerialRx_Char(char c)
{
    // Any received char => reset idle timer
    s_idle_ms = SERIAL_RX_IDLE_TIMEOUT_MS;

    // if dropping until end-of-line, ignore everything until newline
    if (s_drop_until_eol) {
        if (c == '\r' || c == '\n') {
            s_drop_until_eol = false;
        }
        return;
    }

    // Newline => finalize current builder line
    if (c == '\r' || c == '\n') {
        finalize_line_isr();
        return;
    }

    // Ignore NUL
    if ((unsigned char)c == 0u) {
        return;
    }

    // If queue is full and we are building a line -> switch to drop mode
    if (s_q_count >= SERIAL_RX_LINE_QUEUE_LEN) {
        s_drop_until_eol = true;
        s_build_idx = 0u;
        return;
    }

    // Append char into current tail slot
    if (s_build_idx < (SERIAL_RX_BUF_SIZE - 1u)) {
        s_lines[s_q_tail][s_build_idx++] = c;
    } else {
        // buffer full -> finalize immediately
        finalize_line_isr();
        // Now we are at start of next line (if any), but this char is discarded
    }
}

void SerialRx_Tick_1ms(void)
{
    if (s_q_count >= SERIAL_RX_LINE_QUEUE_LEN) return;

    if (s_idle_ms > 0u) {
        s_idle_ms--;
        if (s_idle_ms == 0u) {
            // timeout reached: finalize if have partial data
            finalize_line_isr();
        }
    }
}

bool SerialRx_LineReady(void)
{
    return (s_q_count > 0u);
}

void SerialRx_GetLine(char *out)
{
    if (!out) return;

    uint32_t prim = __get_PRIMASK();
    __disable_irq();

    if (s_q_count == 0u) {
        if (!prim) __enable_irq();
        out[0] = '\0';
        return;
    }

    // copy out head line
    strncpy(out, s_lines[s_q_head], SERIAL_RX_BUF_SIZE - 1u);
    out[SERIAL_RX_BUF_SIZE - 1u] = '\0';

    // clear slot (optional)
    memset(s_lines[s_q_head], 0, SERIAL_RX_BUF_SIZE);

    s_q_head = q_next(s_q_head);
    s_q_count--;

    if (!prim) __enable_irq();
}
