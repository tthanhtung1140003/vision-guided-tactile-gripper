#include "driver/driver.h"
#include "main.h"
#include "stm32f1xx.h"          // GPIO_TypeDef, BSRR, __NOP
#include <stdint.h>

#define SIG_ACTIVE    GPIO_PIN_RESET   // active LOW
#define SIG_IDLE      GPIO_PIN_SET     // idle HIGH

// Số NOP để đảm bảo độ rộng xung STEP (tùy driver)
// TB6600/DM thường chỉ cần vài us; nhưng NOP trên 72MHz rất nhỏ.
// Nếu cần xung rộng hơn: tăng số này hoặc dùng delay theo timer.
#ifndef STEP_PULSE_NOPS
#define STEP_PULSE_NOPS  12u
#endif

static volatile uint8_t s_dir_positive[3] = {1, 1, 1};

/* ===== fast GPIO helpers (BSRR) ===== */
static inline void gpio_write_fast(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState st)
{
    if (st == GPIO_PIN_SET) {
        port->BSRR = (uint32_t)pin;           // set high
    } else {
        port->BSRR = ((uint32_t)pin << 16);   // reset low
    }
}

static inline void step_pulse_low_fast(GPIO_TypeDef *port, uint16_t pin)
{
    // active LOW pulse: LOW then HIGH
    port->BSRR = ((uint32_t)pin << 16);   // LOW
    for (uint32_t i = 0; i < STEP_PULSE_NOPS; i++) {
        __NOP();
    }
    port->BSRR = (uint32_t)pin;           // HIGH
}

void Driver_Enable_All(void)
{
    /* STEP IDLE HIGH */
    gpio_write_fast(X_step_GPIO_Port, X_step_Pin, SIG_IDLE);
    gpio_write_fast(Y_step_GPIO_Port, Y_step_Pin, SIG_IDLE);
    gpio_write_fast(Z_step_GPIO_Port, Z_step_Pin, SIG_IDLE);
}

void Driver_Disable_All(void)
{
    // Nếu bạn có chân EN cho driver: mình sẽ thêm ở đây.
    // Hiện tại để trống theo phần cứng của bạn.
}

void Driver_SetDir(axis_t axis, uint8_t dir_positive)
{
    if (axis > AXIS_Z) return;

    s_dir_positive[axis] = (dir_positive ? 1u : 0u);

    // Theo code bạn: dir_positive -> SIG_IDLE (HIGH), dir_negative -> SIG_ACTIVE (LOW)
    GPIO_PinState st = dir_positive ? SIG_IDLE : SIG_ACTIVE;

    switch (axis)
    {
        case AXIS_X: gpio_write_fast(X_dir_GPIO_Port, X_dir_Pin, st); break;
        case AXIS_Y: gpio_write_fast(Y_dir_GPIO_Port, Y_dir_Pin, st); break;
        case AXIS_Z: gpio_write_fast(Z_dir_GPIO_Port, Z_dir_Pin, st); break;
        default: break;
    }
}

uint8_t Driver_IsDirPositive(axis_t axis)
{
    if (axis > AXIS_Z) return 1u;
    return s_dir_positive[axis];
}

void Driver_Step_Axis(axis_t axis)
{
    switch (axis)
    {
        case AXIS_X: step_pulse_low_fast(X_step_GPIO_Port, X_step_Pin); break;
        case AXIS_Y: step_pulse_low_fast(Y_step_GPIO_Port, Y_step_Pin); break;
        case AXIS_Z: step_pulse_low_fast(Z_step_GPIO_Port, Z_step_Pin); break;
        default: break;
    }
}
