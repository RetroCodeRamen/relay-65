#include "mtarch.h"

void mtarch_init(void) {}
void mtarch_remove(void) {}
void mtarch_start(struct mtarch_thread *thread, void (*function)(void *), void *data)
{
  (void)thread;
  (void)function;
  (void)data;
}
void mtarch_yield(void) {}
void mtarch_exec(struct mtarch_thread *thread) { (void)thread; }
void mtarch_stop(struct mtarch_thread *thread) { (void)thread; }
void mtarch_pstart(void) {}
void mtarch_pstop(void) {}
