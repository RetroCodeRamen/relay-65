#include "contiki.h"
#include "dev/watchdog.h"
#include "dev/serial-line.h"

#ifdef RELAY65_WITH_BASIC
#include "basic.h"
#include "console.h"
#endif

#include <stdio.h>

#define UART_DATA   (*(volatile unsigned char *)0xC000)
#define UART_STATUS (*(volatile unsigned char *)0xC001)
#define UART_RX     0x01

static char linebuf[SERIAL_LINE_CONF_BUFSIZE];
static unsigned char linelen;

static void
poll_uart(void)
{
  while(UART_STATUS & UART_RX) {
    unsigned char c = UART_DATA;
    if(c == '\r') {
      c = '\n';
    }
    putchar(c);
    if(c == '\n') {
      linebuf[linelen] = 0;
      linelen = 0;
#ifdef RELAY65_WITH_BASIC
      console_on_line(linebuf);
#else
      process_post(PROCESS_BROADCAST, serial_line_event_message, linebuf);
#endif
    } else if(linelen < sizeof(linebuf) - 1) {
      linebuf[linelen++] = c;
    }
  }
}

#ifndef RELAY65_WITH_BASIC
PROCINIT(&etimer_process);
#endif

int
main(void)
{
  clock_init();
  rtimer_init();
  watchdog_init();

#ifdef RELAY65_WITH_BASIC
  console_init();
  printf("Contiki on Relay-65\n");
  while(1) {
    poll_uart();
    if(basic_running()) {
      basic_step();
    }
    console_tick();
    watchdog_periodic();
  }
#else
  process_init();
  procinit_init();
  serial_line_init();
  autostart_start(autostart_processes);

  printf("Contiki on Relay-65\n");

  while(1) {
    poll_uart();
    etimer_request_poll();
    process_run();
    watchdog_periodic();
  }
#endif
}
