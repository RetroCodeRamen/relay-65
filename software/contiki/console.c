#include "contiki.h"
#include "basic.h"
#include "console.h"
#include "vfs.h"
#include "man.h"
#include "edit.h"

#include "uart.h"

#define TICK_LO   (*(volatile unsigned char *)0xC020)
#define TICK_HI   (*(volatile unsigned char *)0xC021)
#define TICK_CTRL (*(volatile unsigned char *)0xC022)
#define TICK_IFR  (*(volatile unsigned char *)0xC023)
#define BANK_REG  (*(volatile unsigned char *)0xC010)
#define UART_STAT (*(volatile unsigned char *)0xC001)

extern unsigned char basic_heaptop[];

static unsigned char watch;
static unsigned char in_basic;
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
print_prompt(void)
{
  const char *p = vfs_cwd();
  if(!(p[0] == '/' && p[1] == 0)) {
    uart_puts(p);
  }
  uart_puts("_> ");
}

static void
do_help(void)
{
  uart_puts("Clack - ls cd pwd cat echo edit man help\n"
            "basic time peek poke io bank watch\n"
            "clear uname free hd\n"
            "ls /bin - programs    man NAME - manual\n");
}

static void
do_free(void)
{
  unsigned stack_bot = 0x8000U - 0x0800U;
  unsigned used_end = (unsigned)basic_heaptop;
  unsigned ram_free;
  if(used_end >= stack_bot) {
    ram_free = 0;
  } else {
    ram_free = stack_bot - used_end;
  }
  printf("%u bytes ram  %u free\n", 32768U, ram_free);
}

static void
do_clear(void)
{
  unsigned char i;
  for(i = 0; i < 8; i++) {
    putchar('\n');
  }
}

static void
do_uname(void)
{
  uart_puts("Relay-65 Contiki Clack\n");
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
  if((verb[0] == 'l' || verb[0] == 'L') &&
     (verb[1] == 's' || verb[1] == 'S') && verb[2] == 0) {
    vfs_ls(nexttok(&p));
    return;
  }
  if(cmd_is(verb, "help") || cmd_is(verb, "?")) {
    do_help();
  } else if(cmd_is(verb, "man")) {
    {
      char *t = nexttok(&p);
      if(t == NULL) {
        man_list();
      } else {
        man_show(t);
      }
    }
  } else if(cmd_is(verb, "cd")) {
    vfs_cd(nexttok(&p));
  } else if(cmd_is(verb, "pwd")) {
    vfs_pwd();
  } else if(cmd_is(verb, "cat")) {
    vfs_cat(nexttok(&p));
  } else if(cmd_is(verb, "echo")) {
    while(*p == ' ' || *p == '\t') {
      p++;
    }
    printf("%s\n", p);
  } else if(cmd_is(verb, "edit") || cmd_is(verb, "ed") || cmd_is(verb, "/bin/ed")) {
    edit_start(nexttok(&p));
  } else if(cmd_is(verb, "clear")) {
    do_clear();
  } else if(cmd_is(verb, "uname")) {
    do_uname();
  } else if(cmd_is(verb, "free")) {
    do_free();
  } else if(cmd_is(verb, "hd")) {
    do_peek(&p);
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
  } else if(cmd_is(verb, "basic") || cmd_is(verb, "/bin/basic")) {
    in_basic = 1;
    basic_banner();
    printf("READY\n");
  } else if(cmd_is(verb, "clack") || cmd_is(verb, "/bin/clack")) {
    uart_puts("Clack on Relay-65\n");
  } else {
    printf("? %s  (help)\n", verb);
  }
}

void
console_init(void)
{
  watch = 0;
  in_basic = 0;
  watch_last = 0;
  vfs_init();
  basic_init();
  uart_puts(vfs_file("/etc/motd"));
  print_prompt();
}

void
console_on_line(char *line)
{
  if(edit_active()) {
    if(edit_line(line)) {
      return;
    }
    print_prompt();
    return;
  }
  if(in_basic) {
    if(basic_line(line)) {
      in_basic = 0;
      print_prompt();
    }
    return;
  }
  if((line[0] == 'l' || line[0] == 'L') &&
     (line[1] == 's' || line[1] == 'S') &&
     (line[2] == 0 || line[2] == ' ' || line[2] == '\t')) {
    if(line[2] == 0) {
      vfs_ls(0);
    } else {
      vfs_ls(line + 2);
    }
    print_prompt();
    return;
  }
  run_line(line);
  vfs_ls_sync();
  if(!in_basic && !edit_active()) {
    print_prompt();
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
