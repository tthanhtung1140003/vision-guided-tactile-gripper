#include "comm/comm.h"
#include "usart.h"
#include "stm32f1xx_hal.h"

#include <string.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>

/* ===== config ===== */
#define COMM_RING_SIZE   1024u     // MUST be power-of-two
#define COMM_CHUNK_MAX     64u
#define COMM_RING_MASK   (COMM_RING_SIZE - 1u)

/* ===== log policy ===== */
#define COMM_DROP_INFO_WARN_WHEN_MOTION   1
#define COMM_LOG_RATE_LIMIT_MS           50u

/* ===== ring buffer ===== */
static uint8_t rb[COMM_RING_SIZE];
static volatile uint16_t rb_head = 0;
static volatile uint16_t rb_tail = 0;

static volatile bool tx_busy = false;
static volatile uint16_t tx_len_last = 0;

static volatile uint32_t rb_drop_count = 0;

/* ===== motion active flag (set from motion/system) ===== */
static volatile bool s_motion_active = false;
static uint32_t s_last_log_tick = 0;

void Comm_SetMotionActive(bool active)
{
    s_motion_active = active;
}

static inline uint16_t rb_next(uint16_t v)
{
    return (uint16_t)((v + 1u) & COMM_RING_MASK);
}

static void rb_push(const uint8_t *data, uint16_t len)
{
    for (uint16_t i = 0; i < len; i++)
    {
        uint16_t next = rb_next(rb_head);
        if (next == rb_tail) { rb_drop_count++; return; }
        rb[rb_head] = data[i];
        rb_head = next;
    }
}

static uint16_t rb_available(void)
{
    uint16_t head = rb_head;
    uint16_t tail = rb_tail;

    if (head >= tail) return (uint16_t)(head - tail);
    return (uint16_t)(COMM_RING_SIZE - tail + head);
}

static uint16_t rb_contig_len(void)
{
    uint16_t head = rb_head;
    uint16_t tail = rb_tail;

    if (head >= tail) return (uint16_t)(head - tail);
    return (uint16_t)(COMM_RING_SIZE - tail);
}

void Comm_Init(void)
{
    rb_head = rb_tail = 0;
    tx_busy = false;
    tx_len_last = 0;
    rb_drop_count = 0;

    s_motion_active = false;
    s_last_log_tick = 0;
}

void Comm_SendLog(uint8_t level, const char *msg)
{
    const uint8_t LOG_WARN  = 1;
    const uint8_t LOG_ERROR = 2;

#if COMM_DROP_INFO_WARN_WHEN_MOTION
    /* When motion is active, drop INFO/WARN logs to keep UART free.
       EXCEPTION: allow STATUS lines ("STATE=...") so the GUI can track position in real time. */
    if (s_motion_active && level != LOG_ERROR) {
        if (!(msg && (strncmp(msg, "STATE=", 6) == 0 || strncmp(msg, "OK ", 3) == 0 || strncmp(msg, "BUSY ", 5) == 0))) {
            return;
        }
    }
#endif

    if (s_motion_active)
    {
        uint32_t now = HAL_GetTick();
        if ((now - s_last_log_tick) < COMM_LOG_RATE_LIMIT_MS) {
            return;
        }
        s_last_log_tick = now;
    }

    char line[160];
    const char *lvl = "INFO";
    if (level == LOG_WARN) lvl = "WARN";
    else if (level == LOG_ERROR) lvl = "ERROR";

    int n = snprintf(line, sizeof(line), "[%s] %s\r\n", lvl, msg ? msg : "");
    if (n <= 0) return;
    if (n > (int)sizeof(line)) n = (int)sizeof(line);

    rb_push((const uint8_t*)line, (uint16_t)n);
}

void Comm_Task(void)
{
    if (tx_busy) return;

    uint16_t avail = rb_available();
    if (avail == 0) return;

    uint16_t chunk = rb_contig_len();
    if (chunk > COMM_CHUNK_MAX) chunk = COMM_CHUNK_MAX;

    __disable_irq();
    if (tx_busy) { __enable_irq(); return; }
    tx_busy = true;
    tx_len_last = chunk;
    __enable_irq();

    if (HAL_UART_Transmit_IT(&huart1, (uint8_t*)&rb[rb_tail], chunk) != HAL_OK)
    {
        __disable_irq();
        tx_busy = false;
        tx_len_last = 0;
        __enable_irq();
    }
}

void Comm_OnTxCpltISR(void)
{
    if (!tx_busy) return;

    rb_tail = (uint16_t)((rb_tail + tx_len_last) & COMM_RING_MASK);
    tx_busy = false;
    tx_len_last = 0;
}
