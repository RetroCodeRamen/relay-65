#ifndef RELAY65_BASIC_H_
#define RELAY65_BASIC_H_

void basic_init(void);
void basic_banner(void);
/* 0 = stay in BASIC, 1 = BYE back to the monitor. */
int basic_line(char *line);
int basic_running(void);
void basic_step(void);

#endif
