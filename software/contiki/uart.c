#include "uart.h"

#include <stdarg.h>

static void
hex(unsigned v, unsigned width)
{
  char buf[4];
  unsigned n = 0;
  do {
    unsigned d = v & 15;
    buf[n++] = (char)(d < 10 ? '0' + d : 'a' + (d - 10));
    v >>= 4;
  } while(v && n < 4);
  while(n < width && n < 4) {
    buf[n++] = '0';
  }
  while(n) {
    uart_putc(buf[--n]);
  }
}

static void
udec(unsigned long v)
{
  char buf[10];
  unsigned n = 0;
  if(v == 0) {
    uart_putc('0');
    return;
  }
  while(v && n < 10) {
    buf[n++] = (char)('0' + (v % 10));
    v /= 10;
  }
  while(n) {
    uart_putc(buf[--n]);
  }
}

void
uart_printf(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  while(*fmt) {
    unsigned width;
    const char *run;
    if(*fmt != '%') {
      run = fmt;
      while(*fmt && *fmt != '%') {
        fmt++;
      }
      uart_putn(run, (unsigned)(fmt - run));
      continue;
    }
    fmt++;
    width = 0;
    if(*fmt == '0') {
      fmt++;
      while(*fmt >= '0' && *fmt <= '9') {
        width = (unsigned)(*fmt - '0') + width * 10;
        fmt++;
      }
    }
    if(*fmt == 's') {
      const char *s = va_arg(ap, char *);
      uart_puts(s == NULL ? "" : s);
    } else if(*fmt == 'c') {
      uart_putc((char)va_arg(ap, int));
    } else if(*fmt == 'd' || *fmt == 'u') {
      udec((unsigned)va_arg(ap, int));
    } else if(*fmt == 'l' && (fmt[1] == 'u' || fmt[1] == 'd')) {
      fmt++;
      udec(va_arg(ap, unsigned long));
    } else if(*fmt == 'x' || *fmt == 'X') {
      hex((unsigned)va_arg(ap, int), width);
    } else if(*fmt == '%') {
      uart_putc('%');
    }
    if(*fmt) {
      fmt++;
    }
  }
  va_end(ap);
}
