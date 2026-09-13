#ifndef RELAY65_UART_H_
#define RELAY65_UART_H_

#include <stddef.h>

/* Direct UART, not cc65 stdio. printf() here is uart_printf(). */

void __fastcall__ uart_putc(char c);
void __fastcall__ uart_puts(const char *s);
void __fastcall__ uart_putn(const char *s, unsigned n);
void __fastcall__ uart_read_line(char *buf);
unsigned char __fastcall__ uart_getc(void);
void uart_delay10(void);
void uart_printf(const char *fmt, ...);

#define printf uart_printf
#define putchar uart_putc
#define puts uart_puts

#endif
