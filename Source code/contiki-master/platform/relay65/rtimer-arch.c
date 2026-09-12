#include "sys/rtimer.h"

void
rtimer_arch_init(void)
{
}

void
rtimer_arch_schedule(rtimer_clock_t t)
{
  (void)t;
}
