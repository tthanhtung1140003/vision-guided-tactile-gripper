#ifndef JOG_H
#define JOG_H

typedef enum {
    JOG_X_POS,
    JOG_X_NEG,
    JOG_Y_POS,
    JOG_Y_NEG,
    JOG_Z_POS,
    JOG_Z_NEG
} jog_dir_t;

void Jog_Init(void);
void Jog_SetStep(float step_mm);
void Jog_Execute(jog_dir_t dir);

#endif
