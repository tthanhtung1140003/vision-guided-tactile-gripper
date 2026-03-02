#include "protocol/protocol.h"
#include "serial_rx.h"
#include "motion/motion.h"
#include "homing/homing.h"
#include "jog/jog.h"
#include "system/system.h"
#include "comm/comm.h"
#include "error/error.h"
#include "stm32f1xx_hal.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <math.h>

static protocol_cmd_packet_t cmd;
static bool cmd_pending = false;

/* ===== pending queue (to survive bursts while motion busy) ===== */
static float s_jog_pending_x = 0.0f;
static float s_jog_pending_y = 0.0f;
static float s_jog_pending_z = 0.0f;
static bool  s_move_pending = false;
static protocol_cmd_packet_t s_move_cmd;

/* ===== tracking velocity pending (TVEL) ===== */
static bool s_tvel_pending = false;
static protocol_cmd_packet_t s_tvel_cmd;

/* ===== STATUS rate limit (khi đang chạy) ===== */
#define STATUS_RATE_LIMIT_MS   100u

static uint32_t s_last_status_ms = 0;

/* ===== helper: đang ở trạng thái nhạy (đang chạy) ===== */
static inline bool protocol_motion_sensitive(void)
{
    system_state_t st = System_State_Get();
    if (st == SYS_MOVING || st == SYS_JOGGING || st == SYS_HOMING) return true;
    if (Motion_IsActive()) return true;
    return false;
}

protocol_report_t Protocol_GetReport(void)
{
    protocol_report_t r;
    r.state = (uint8_t)System_State_Get();
    r.error = (uint32_t)sys_error;
    Motion_GetPosition(&r.pos_x, &r.pos_y, &r.pos_z);
    Motion_GetAxisSpeeds(&r.spd_x, &r.spd_y, &r.spd_z);
    return r;
}

static void parse_move(char *line)
{
    char *p;

    cmd.cmd   = CMD_MOVE_ABS;
    cmd.use_x = cmd.use_y = cmd.use_z = false;

    if ((p = strchr(line, 'X'))) { cmd.x = strtof(p + 1, NULL); cmd.use_x = true; }
    if ((p = strchr(line, 'Y'))) { cmd.y = strtof(p + 1, NULL); cmd.use_y = true; }
    if ((p = strchr(line, 'Z'))) { cmd.z = strtof(p + 1, NULL); cmd.use_z = true; }

    if (!cmd.use_x && !cmd.use_y && !cmd.use_z) return;
    cmd_pending = true;
}

static void parse_jog(char *line)
{
    char axis, sign;
    float step;

    if (sscanf(line, "JOG %c%c%f", &axis, &sign, &step) != 3) return;

    axis = (char)toupper((unsigned char)axis);

    cmd.cmd = CMD_JOG;
    cmd.jog_step = step;

    switch (axis)
    {
        case 'X': cmd.jog_dir = (sign == '-') ? JOG_X_NEG : JOG_X_POS; break;
        case 'Y': cmd.jog_dir = (sign == '-') ? JOG_Y_NEG : JOG_Y_POS; break;
        case 'Z': cmd.jog_dir = (sign == '-') ? JOG_Z_NEG : JOG_Z_POS; break;
        default: return;
    }

    cmd_pending = true;
}

static void parse_tvel(char *line)
{
    /* Format: TVEL X+40.0 Y-10.0 Z+0.0  (axis optional) */
    cmd.cmd = CMD_TVEL;
    cmd.use_vx = cmd.use_vy = cmd.use_vz = false;

    char *p;
    if ((p = strchr(line, 'X')))
    {
        cmd.vx = strtof(p + 1, NULL);
        cmd.use_vx = true;
    }
    if ((p = strchr(line, 'Y')))
    {
        cmd.vy = strtof(p + 1, NULL);
        cmd.use_vy = true;
    }
    if ((p = strchr(line, 'Z')))
    {
        cmd.vz = strtof(p + 1, NULL);
        cmd.use_vz = true;
    }

    if (!cmd.use_vx && !cmd.use_vy && !cmd.use_vz)
    {
        /* allow TVEL with no axes as zero */
        cmd.use_vx = cmd.use_vy = cmd.use_vz = true;
        cmd.vx = cmd.vy = cmd.vz = 0.0f;
    }
    cmd_pending = true;
}

void Protocol_ParseLine(char *line)
{
    if (!line || line[0] == '\0') return;

    /* simple commands */
    if (strcmp(line, "STATUS") == 0 || strcmp(line, "?") == 0)
    {
        cmd.cmd = CMD_STATUS;
        cmd_pending = true;
    }
    else if (strcmp(line, "ACK") == 0 || strcmp(line, "RESET") == 0)
    {
        cmd.cmd = CMD_ACK;
        cmd_pending = true;
    }
    else if (strcmp(line, "HOME") == 0)
    {
        cmd.cmd = CMD_HOME;
        cmd_pending = true;
    }
    else if (strcmp(line, "STOP") == 0)
    {
        cmd.cmd = CMD_STOP;
        cmd_pending = true;
    }
    else if (strcmp(line, "TSTOP") == 0)
    {
        cmd.cmd = CMD_TSTOP;
        cmd_pending = true;
    }
    else if (strncmp(line, "MOVE", 4) == 0)
    {
        parse_move(line);
    }
    else if (strncmp(line, "JOG", 3) == 0)
    {
        parse_jog(line);
    }
    else if (strncmp(line, "TVEL", 4) == 0)
    {
        parse_tvel(line);
    }
    else
    {
        /* Tránh log spam khi đang chạy */
        if (!protocol_motion_sensitive())
            Comm_SendLog(LOG_WARN, "Unknown CMD");
    }
}

void Protocol_Task(void)
{
    char line[64];

    /* ===== Drain RX queue: parse+execute each line (no overwrite) ===== */
    while (SerialRx_LineReady())
    {
        SerialRx_GetLine(line);

        /* Echo RX only when idle to avoid UART burst */
        if (!protocol_motion_sensitive())
        {
            Comm_SendLog(LOG_INFO, line);
        }

        Protocol_ParseLine(line);

        if (cmd_pending)
        {
            /* Safety gating: when ERROR or STOPPED, only allow STATUS / ACK / STOP */
            system_state_t st0 = System_State_Get();
            if ((st0 == SYS_ERROR || st0 == SYS_STOPPED) &&
                cmd.cmd != CMD_STATUS && cmd.cmd != CMD_ACK && cmd.cmd != CMD_STOP)
            {
                Comm_SendLog(LOG_INFO, "BUSY LOCKED");
                cmd_pending = false;
                continue;
            }

            switch (cmd.cmd)
            {
                case CMD_STATUS:
                {
                    if (protocol_motion_sensitive())
                    {
                        uint32_t now = HAL_GetTick();
                        if ((now - s_last_status_ms) < STATUS_RATE_LIMIT_MS)
                        {
                            /* silent drop */
                            break;
                        }
                        s_last_status_ms = now;
                    }
                    else
                    {
                        s_last_status_ms = HAL_GetTick();
                    }

                    protocol_report_t r = Protocol_GetReport();
                    char msg[160];
                    snprintf(msg, sizeof(msg),
                             "STATE=%u ERR=%lu POS=%.3f,%.3f,%.3f SPD=%.3f,%.3f,%.3f",
                             (unsigned)r.state, (unsigned long)r.error,
                             (double)r.pos_x, (double)r.pos_y, (double)r.pos_z,
                             (double)r.spd_x, (double)r.spd_y, (double)r.spd_z);

                    Comm_SendLog(LOG_INFO, msg);
                    break;
                }

                case CMD_ACK:
                    System_Acknowledge();
                    Comm_SendLog(LOG_INFO, "OK ACK");
                    break;

                case CMD_HOME:
                    if (!protocol_motion_sensitive())
                        System_Log(LOG_INFO, "CMD HOME");
                    Homing_Start();
                    Comm_SendLog(LOG_INFO, "OK HOME");
                    break;

                case CMD_MOVE_ABS:
                    if (!protocol_motion_sensitive())
                        System_Log(LOG_INFO, "CMD MOVE");

                    if (System_IsBusy())
                    {
                        /* keep last MOVE request; will run when idle */
                        s_move_cmd = cmd;
                        s_move_pending = true;
                        Comm_SendLog(LOG_INFO, "OK MOVE QUEUED");
                        break;
                    }

                    System_State_Set(SYS_MOVING);
                    Motion_MoveTo(cmd.use_x, cmd.use_y, cmd.use_z, cmd.x, cmd.y, cmd.z);
                    Comm_SendLog(LOG_INFO, "OK MOVE");
                    break;

                case CMD_JOG:
                {
                    if (!protocol_motion_sensitive())
                        System_Log(LOG_INFO, "CMD JOG");

                    float signed_step = (cmd.jog_dir == JOG_X_NEG || cmd.jog_dir == JOG_Y_NEG || cmd.jog_dir == JOG_Z_NEG)
                                      ? (-cmd.jog_step) : (cmd.jog_step);

                    if (System_IsBusy())
                    {
                        /* accumulate jog delta while busy; will execute when idle */
                        switch (cmd.jog_dir)
                        {
                            case JOG_X_POS: case JOG_X_NEG: s_jog_pending_x += signed_step; break;
                            case JOG_Y_POS: case JOG_Y_NEG: s_jog_pending_y += signed_step; break;
                            case JOG_Z_POS: case JOG_Z_NEG: s_jog_pending_z += signed_step; break;
                            default: break;
                        }
                        Comm_SendLog(LOG_INFO, "OK JOG QUEUED");
                        break;
                    }

                    Jog_SetStep(cmd.jog_step);
                    Jog_Execute(cmd.jog_dir);
                    Comm_SendLog(LOG_INFO, "OK JOG");
                    break;
                }

                case CMD_TVEL:
                {
                    /* TVEL must be applied immediately during tracking (SYS_JOGGING).
                       If we queue while SYS_JOGGING, heartbeat TVEL commands will never be flushed,
                       causing jerky motion and watchdog stops.
                       Only defer TVEL when a discrete MOVE/HOME is running. */
                    system_state_t st_now = System_State_Get();

                    if (st_now == SYS_MOVING || st_now == SYS_HOMING)
                    {
                        s_tvel_cmd = cmd;
                        s_tvel_pending = true;
                        Comm_SendLog(LOG_INFO, "OK TVEL QUEUED");
                        break;
                    }

                    System_State_Set(SYS_JOGGING);
                    Motion_Track_SetVel(cmd.use_vx, cmd.use_vy, cmd.use_vz, cmd.vx, cmd.vy, cmd.vz);
                    if (!protocol_motion_sensitive()) { Comm_SendLog(LOG_INFO, "OK TVEL"); }
                    break;
                }

                case CMD_TSTOP:
                    /* Soft stop: do not enter SYS_STOPPED */
                    Motion_Track_SetVel(true, true, true, 0.0f, 0.0f, 0.0f);
                    if (System_State_Get() == SYS_JOGGING) System_State_Set(SYS_IDLE);
                    if (!protocol_motion_sensitive()) { Comm_SendLog(LOG_INFO, "OK TSTOP"); }
                    break;

                case CMD_STOP:
                    System_Log(LOG_WARN, "CMD STOP");
                    System_Stop();
                    Comm_SendLog(LOG_INFO, "OK STOP");
                    break;

                default:
                    break;
            }

            cmd_pending = false;
        }
    }

    /* ===== When idle, flush queued MOVE/JOG (priority: MOVE then JOG) ===== */
    if (System_IsBusy()) return;

    system_state_t st = System_State_Get();
    if (st == SYS_ERROR || st == SYS_STOPPED) return;

    if (s_move_pending)
    {
        s_move_pending = false;
        System_State_Set(SYS_MOVING);
        Motion_MoveTo(s_move_cmd.use_x, s_move_cmd.use_y, s_move_cmd.use_z,
                      s_move_cmd.x, s_move_cmd.y, s_move_cmd.z);
        Comm_SendLog(LOG_INFO, "OK MOVE FLUSH");
        return;
    }

    if (s_tvel_pending)
    {
        s_tvel_pending = false;
        System_State_Set(SYS_JOGGING);
        Motion_Track_SetVel(s_tvel_cmd.use_vx, s_tvel_cmd.use_vy, s_tvel_cmd.use_vz,
                            s_tvel_cmd.vx, s_tvel_cmd.vy, s_tvel_cmd.vz);
        Comm_SendLog(LOG_INFO, "OK TVEL FLUSH");
        return;
    }

    /* flush one-axis jog per call to keep motion stable */
    if (s_jog_pending_x != 0.0f)
    {
        float d = s_jog_pending_x;
        s_jog_pending_x = 0.0f;
        Jog_SetStep(fabsf(d));
        Jog_Execute(d >= 0.0f ? JOG_X_POS : JOG_X_NEG);
        Comm_SendLog(LOG_INFO, "OK JOG FLUSH");
        return;
    }
    if (s_jog_pending_y != 0.0f)
    {
        float d = s_jog_pending_y;
        s_jog_pending_y = 0.0f;
        Jog_SetStep(fabsf(d));
        Jog_Execute(d >= 0.0f ? JOG_Y_POS : JOG_Y_NEG);
        Comm_SendLog(LOG_INFO, "OK JOG FLUSH");
        return;
    }
    if (s_jog_pending_z != 0.0f)
    {
        float d = s_jog_pending_z;
        s_jog_pending_z = 0.0f;
        Jog_SetStep(fabsf(d));
        Jog_Execute(d >= 0.0f ? JOG_Z_POS : JOG_Z_NEG);
        Comm_SendLog(LOG_INFO, "OK JOG FLUSH");
        return;
    }
}

void Protocol_Init(void)
{
    cmd_pending = false;
    s_last_status_ms = 0;
    s_jog_pending_x = s_jog_pending_y = s_jog_pending_z = 0.0f;
    s_move_pending = false;
    s_tvel_pending = false;
}
