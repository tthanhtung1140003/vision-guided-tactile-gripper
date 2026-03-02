#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#include "jog/jog.h"

/* ===== COMMAND ID ===== */
typedef enum {
    CMD_NONE = 0,
    CMD_STATUS,
    CMD_ACK,
    CMD_JOG,
    CMD_MOVE_ABS,
    CMD_HOME,
    CMD_STOP,
    CMD_TVEL,
    CMD_TSTOP
} protocol_cmd_t;

/* ===== COMMAND STRUCT ===== */
typedef struct {
    protocol_cmd_t cmd;

    /* jog */
    jog_dir_t jog_dir;
    float jog_step;

    /* move absolute */
    bool use_x;
    bool use_y;
    bool use_z;
    float x;
    float y;
    float z;

    /* tracking velocity (mm/s) */
    bool use_vx;
    bool use_vy;
    bool use_vz;
    float vx;
    float vy;
    float vz;

} protocol_cmd_packet_t;

/* ===== SYSTEM REPORT ===== */
typedef struct {
    uint8_t state;
    uint32_t error;
    float pos_x;
    float pos_y;
    float pos_z;

    float spd_x;
    float spd_y;
    float spd_z;
} protocol_report_t;

/* ===== API ===== */
void Protocol_Init(void);
void Protocol_Task(void);
protocol_report_t Protocol_GetReport(void);

/* ===== ASCII PARSER ===== */
void Protocol_ParseLine(char *line);

#endif
