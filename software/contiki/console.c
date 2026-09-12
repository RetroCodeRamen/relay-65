#include "contiki.h"
#include "basic.h"
#include "console.h"

#include <stdio.h>

#define TICK_LO   (*(volatile unsigned char *)0xC020)
#define TICK_HI   (*(volatile unsigned char *)0xC021)
#define TICK_CTRL (*(volatile unsigned char *)0xC022)
#define TICK_IFR  (*(volatile unsigned char *)0xC023)
#define BANK_REG  (*(volatile unsigned char *)0xC010)
#define UART_STAT (*(volatile unsigned char *)0xC001)

static unsigned char watch;
static unsigned char in_basic;
static char cmd[SERIAL_LINE_CONF_BUFSIZE];
static clock_time_t watch_last;

static char
lower(char c)
{
  if(c >= 'A' && c <= 'Z') {
    return (char)(c + 32);
  }
  return c;
}

static char *
nexttok(char **pp)
{
  char *p = *pp;
  while(*p == ' ' || *p == '\t') {
    p++;
  }
  if(*p == 0) {
    *pp = p;
    return NULL;
  }
  {
    char *s = p;
    while(*p && *p != ' ' && *p != '\t') {
      p++;
    }
    if(*p) {
      *p++ = 0;
    }
    *pp = p;
    return s;
  }
}

static int
cmd_is(const char *a, const char *b)
{
  while(*a && *b) {
    if(lower(*a) != lower(*b)) {
      return 0;
    }
    a++;
    b++;
  }
  return *a == 0 && *b == 0;
}

static int
parsehex(const char *s, unsigned *out)
{
  unsigned v = 0;
  unsigned n = 0;
  if(s == NULL || *s == 0) {
    return 0;
  }
  if(*s == '$') {
    s++;
  }
  if(s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
    s += 2;
  }
  while(*s) {
    unsigned d;
    char c = *s++;
    if(c >= '0' && c <= '9') {
      d = (unsigned)(c - '0');
    } else if(c >= 'a' && c <= 'f') {
      d = (unsigned)(c - 'a' + 10);
    } else if(c >= 'A' && c <= 'F') {
      d = (unsigned)(c - 'A' + 10);
    } else {
      return 0;
    }
    v = (v << 4) + d;
    n++;
  }
  if(n == 0) {
    return 0;
  }
  *out = v;
  return 1;
}

static void
copy_line(const char *src)
{
  unsigned i;
  for(i = 0; i < sizeof(cmd) - 1 && src[i] != 0; i++) {
    cmd[i] = src[i];
  }
  cmd[i] = 0;
}

static void
do_help(void)
{
  printf("help time peek poke io bank watch basic\n");
  printf("peek ADDR [N]  poke ADDR BYTES..\n");
  printf("ADDR hex, optional $\n");
}

static void
do_bank(char **pp)
{
  char *a = nexttok(pp);
  unsigned v;
  if(a == NULL) {
    printf("bank %02x\n", BANK_REG);
    return;
  }
  if(!parsehex(a, &v) || v > 0xFF) {
    printf("usage: bank [NN]\n");
    return;
  }
  BANK_REG = (unsigned char)v;
  printf("bank %02x\n", BANK_REG);
}

static void
do_time(void)
{
  unsigned char hi, lo;
  do {
    hi = TICK_HI;
    lo = TICK_LO;
  } while(hi != TICK_HI);
  printf("clock %u  sec %lu  tick %u\n",
         (unsigned)clock_time(),
         clock_seconds(),
         (unsigned)((hi << 8) | lo));
}

static void
do_io(void)
{
  unsigned char hi, lo;
  do {
    hi = TICK_HI;
    lo = TICK_LO;
  } while(hi != TICK_HI);
  printf("uart $C001=%02x  bank $C010=%02x\n", UART_STAT, BANK_REG);
  printf("tick %02x%02x ctrl %02x ifr %02x\n", hi, lo, TICK_CTRL, TICK_IFR);
}

static void
do_peek(char **pp)
{
  char *a = nexttok(pp);
  char *narg = nexttok(pp);
  unsigned addr, count, i;
  if(!parsehex(a, &addr)) {
    printf("usage: peek ADDR [N]\n");
    return;
  }
  count = 1;
  if(narg != NULL && !parsehex(narg, &count)) {
    printf("usage: peek ADDR [N]\n");
    return;
  }
  if(count == 0) {
    count = 1;
  }
  if(count > 16) {
    count = 16;
  }
  printf("%04x:", addr);
  for(i = 0; i < count; i++) {
    unsigned char v = *(volatile unsigned char *)(addr + i);
    printf(" %02x", v);
  }
  printf("\n");
}

static void
do_poke(char **pp)
{
  char *a = nexttok(pp);
  unsigned addr, n;
  if(!parsehex(a, &addr)) {
    printf("usage: poke ADDR BYTES..\n");
    return;
  }
  n = 0;
  while(1) {
    char *b = nexttok(pp);
    unsigned v;
    if(b == NULL) {
      break;
    }
    if(!parsehex(b, &v) || v > 0xFF) {
      printf("bad byte\n");
      return;
    }
    *(volatile unsigned char *)(addr + n) = (unsigned char)v;
    n++;
  }
  if(n == 0) {
    printf("usage: poke ADDR BYTES..\n");
    return;
  }
  printf("wrote %u @ %04x\n", n, addr);
}

static void
do_watch(char **pp)
{
  char *a = nexttok(pp);
  if(a == NULL || cmd_is(a, "on")) {
    watch = 1;
    printf("watch on\n");
  } else if(cmd_is(a, "off")) {
    watch = 0;
    printf("watch off\n");
  } else {
    printf("usage: watch [on|off]\n");
  }
}

static void
run_line(char *line)
{
  char *p = line;
  char *verb = nexttok(&p);
  if(verb == NULL) {
    return;
  }
  if(cmd_is(verb, "help") || cmd_is(verb, "?")) {
    do_help();
  } else if(cmd_is(verb, "time")) {
    do_time();
  } else if(cmd_is(verb, "io")) {
    do_io();
  } else if(cmd_is(verb, "peek")) {
    do_peek(&p);
  } else if(cmd_is(verb, "poke")) {
    do_poke(&p);
  } else if(cmd_is(verb, "watch")) {
    do_watch(&p);
  } else if(cmd_is(verb, "bank")) {
    do_bank(&p);
  } else if(cmd_is(verb, "basic")) {
    in_basic = 1;
    basic_banner();
    printf("READY\n");
  } else {
    printf("? %s  (help)\n", verb);
  }
}

void
console_init(void)
{
  watch = 0;
  in_basic = 0;
  watch_last = clock_time();
  basic_init();
  basic_banner();
  printf("console ready - type basic or help\n");
}

void
console_on_line(char *line)
{
  copy_line(line);
  if(in_basic) {
    if(basic_line(cmd)) {
      in_basic = 0;
    }
  } else {
    run_line(cmd);
  }
}

void
console_tick(void)
{
  clock_time_t now;
  if(!watch) {
    return;
  }
  now = clock_time();
  if((clock_time_t)(now - watch_last) >= CLOCK_SECOND) {
    watch_last = now;
    printf("[clock %u]\n", (unsigned)now);
  }
}
