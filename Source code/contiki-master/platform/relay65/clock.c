#include "contiki.h"

#define TICK_LO (*(volatile unsigned char *)0xC020)
#define TICK_HI (*(volatile unsigned char *)0xC021)

static unsigned long seconds;
static clock_time_t last;

static clock_time_t
hw_ticks(void)
{
  unsigned char hi, lo;
  do {
    hi = TICK_HI;
    lo = TICK_LO;
  } while(hi != TICK_HI);
  return (clock_time_t)((hi << 8) | lo);
}

#define TICK_CTRL (*(volatile unsigned char *)0xC022)

void
clock_init(void)
{
  last = hw_ticks();
  seconds = 0;
  __asm__("sei");
  TICK_CTRL = 0x01;
}

clock_time_t
clock_time(void)
{
  return hw_ticks();
}

unsigned long
clock_seconds(void)
{
  clock_time_t now = hw_ticks();
  seconds += (unsigned short)(now - last) / CLOCK_SECOND;
  last = now;
  return seconds;
}

void
clock_set_seconds(unsigned long sec)
{
  seconds = sec;
}

void
clock_wait(clock_time_t t)
{
  clock_time_t start = clock_time();
  while((clock_time_t)(clock_time() - start) < t) {
  }
}

void
clock_delay_usec(uint16_t dt)
{
  (void)dt;
}

void
clock_delay(unsigned int delay)
{
  clock_wait((clock_time_t)delay);
}

int
clock_fine_max(void)
{
  return 0;
}

unsigned short
clock_fine(void)
{
  return 0;
}
