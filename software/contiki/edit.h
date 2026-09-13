#ifndef RELAY65_EDIT_H_
#define RELAY65_EDIT_H_

void edit_start(const char *path);
int edit_active(void);
/* 1 = still editing, 0 = done (saved or error). */
int edit_line(const char *line);

#endif
