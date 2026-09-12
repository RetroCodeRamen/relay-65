#include "basic.h"

#include <stdio.h>

#define MAXLINES 24
#define LINELEN  40
#define GOSUBMAX 6

#define BASIC_NAME "RELAY65 BASIC"
#define BASIC_VER  "V1.0"

/* $0000-$7FFF is the software-visible 32K. Stack grows down from $8000. */
#define RAM_BYTES   32768U
#define STACK_TOP   0x8000U
#define STACK_BYTES 0x0800U

/* First unused RAM after BSS; exported from crt0 as basic_heaptop. */
extern unsigned char basic_heaptop[];

static int vars[26];
static unsigned char nlines;
static unsigned lineno[MAXLINES];
static char linetxt[MAXLINES][LINELEN];

static unsigned char running;
static unsigned char pc;
static unsigned char gsp;
static unsigned gchar[GOSUBMAX];
static unsigned char waiting;
static unsigned char waitvar;
static unsigned char print_nl;

static char *cur;
static unsigned char failed;

static char
lower(char c)
{
  if(c >= 'A' && c <= 'Z') {
    return (char)(c + 32);
  }
  return c;
}

static void
pr_uint(unsigned v)
{
  char buf[6];
  unsigned char n = 0;
  if(v == 0) {
    putchar('0');
    return;
  }
  while(v) {
    buf[n++] = (char)('0' + (v % 10));
    v = v / 10;
  }
  while(n) {
    putchar(buf[--n]);
  }
}

static void
pr_int(int v)
{
  if(v < 0) {
    putchar('-');
    pr_uint((unsigned)-v);
  } else {
    pr_uint((unsigned)v);
  }
}

static void
skip(void)
{
  while(*cur == ' ' || *cur == '\t') {
    cur++;
  }
}

static void
fail(const char *m)
{
  failed = 1;
  running = 0;
  waiting = 0;
  printf("! %s\n", m);
}

static int
kw(const char *k)
{
  char *s;
  skip();
  s = cur;
  while(*k) {
    if(lower(*s) != *k) {
      return 0;
    }
    s++;
    k++;
  }
  if((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z')) {
    return 0;
  }
  cur = s;
  return 1;
}

static int expr(void);

static int
parsenum(void)
{
  int v = 0;
  unsigned n = 0;
  skip();
  if(*cur == '$') {
    cur++;
    while(1) {
      char c = *cur;
      unsigned d;
      if(c >= '0' && c <= '9') {
        d = (unsigned)(c - '0');
      } else if(c >= 'a' && c <= 'f') {
        d = (unsigned)(c - 'a' + 10);
      } else if(c >= 'A' && c <= 'F') {
        d = (unsigned)(c - 'A' + 10);
      } else {
        break;
      }
      v = (int)(((unsigned)v << 4) + d);
      cur++;
      n++;
    }
    if(n == 0) {
      fail("num");
      return 0;
    }
    return v;
  }
  if(*cur < '0' || *cur > '9') {
    fail("num");
    return 0;
  }
  while(*cur >= '0' && *cur <= '9') {
    v = v * 10 + (*cur - '0');
    cur++;
  }
  return v;
}

static int
factor(void)
{
  int v;
  skip();
  if(*cur == '-') {
    cur++;
    return -factor();
  }
  if(*cur == '(') {
    cur++;
    v = expr();
    skip();
    if(*cur != ')') {
      fail(")");
      return 0;
    }
    cur++;
    return v;
  }
  if(kw("peek")) {
    skip();
    if(*cur != '(') {
      fail("peek");
      return 0;
    }
    cur++;
    v = expr();
    skip();
    if(*cur != ')') {
      fail("peek");
      return 0;
    }
    cur++;
    return (int)(*(volatile unsigned char *)(unsigned)v);
  }
  if((*cur >= 'a' && *cur <= 'z') || (*cur >= 'A' && *cur <= 'Z')) {
    v = vars[lower(*cur) - 'a'];
    cur++;
    return v;
  }
  return parsenum();
}

static int
term(void)
{
  int v = factor();
  while(!failed) {
    skip();
    if(*cur == '*') {
      cur++;
      v = v * factor();
    } else if(*cur == '/') {
      cur++;
      {
        int r = factor();
        if(r == 0) {
          fail("div0");
          return 0;
        }
        v = v / r;
      }
    } else {
      break;
    }
  }
  return v;
}

static int
expr(void)
{
  int v = term();
  while(!failed) {
    skip();
    if(*cur == '+') {
      cur++;
      v = v + term();
    } else if(*cur == '-') {
      cur++;
      v = v - term();
    } else {
      break;
    }
  }
  return v;
}

static int
relop(int *op)
{
  skip();
  if(cur[0] == '<' && cur[1] == '>') {
    cur += 2;
    *op = 1;
    return 1;
  }
  if(cur[0] == '<' && cur[1] == '=') {
    cur += 2;
    *op = 2;
    return 1;
  }
  if(cur[0] == '>' && cur[1] == '=') {
    cur += 2;
    *op = 3;
    return 1;
  }
  if(*cur == '=') {
    cur++;
    *op = 0;
    return 1;
  }
  if(*cur == '<') {
    cur++;
    *op = 4;
    return 1;
  }
  if(*cur == '>') {
    cur++;
    *op = 5;
    return 1;
  }
  return 0;
}

static int
reltrue(int a, int op, int b)
{
  if(op == 0) {
    return a == b;
  }
  if(op == 1) {
    return a != b;
  }
  if(op == 2) {
    return a <= b;
  }
  if(op == 3) {
    return a >= b;
  }
  if(op == 4) {
    return a < b;
  }
  return a > b;
}

static int
findline(unsigned n)
{
  unsigned char i;
  for(i = 0; i < nlines; i++) {
    if(lineno[i] == n) {
      return (int)i;
    }
  }
  return -1;
}

static void
exec_stmt(void);

static void
do_goto(unsigned n)
{
  int i = findline(n);
  if(i < 0) {
    fail("goto");
    return;
  }
  pc = (unsigned char)i;
}

static void
do_print(void)
{
  print_nl = 1;
  skip();
  if(*cur == 0) {
    printf("\n");
    return;
  }
  while(!failed && *cur) {
    skip();
    if(*cur == 0) {
      break;
    }
    if(*cur == '"') {
      cur++;
      while(*cur && *cur != '"') {
        putchar(*cur++);
      }
      if(*cur == '"') {
        cur++;
      }
      print_nl = 1;
    } else {
      pr_int(expr());
      print_nl = 1;
    }
    skip();
    if(*cur == ';') {
      cur++;
      print_nl = 0;
    } else if(*cur == ',') {
      cur++;
      putchar(' ');
      print_nl = 1;
    } else {
      break;
    }
  }
  if(print_nl) {
    printf("\n");
  }
}

static void
do_let(void)
{
  int slot;
  skip();
  if(!((*cur >= 'a' && *cur <= 'z') || (*cur >= 'A' && *cur <= 'Z'))) {
    fail("let");
    return;
  }
  slot = lower(*cur) - 'a';
  cur++;
  skip();
  if(*cur != '=') {
    fail("=");
    return;
  }
  cur++;
  vars[slot] = expr();
}

static void
do_list(void)
{
  unsigned char i;
  for(i = 0; i < nlines; i++) {
    pr_uint(lineno[i]);
    putchar(' ');
    printf("%s\n", linetxt[i]);
  }
}

static void
store_line(unsigned n, char *text)
{
  int i;
  skip();
  while(*text == ' ') {
    text++;
  }
  if(*text == 0) {
    i = findline(n);
    if(i >= 0) {
      unsigned char j;
      for(j = (unsigned char)i; j + 1 < nlines; j++) {
        lineno[j] = lineno[j + 1];
        {
          unsigned char k;
          for(k = 0; k < LINELEN; k++) {
            linetxt[j][k] = linetxt[j + 1][k];
          }
        }
      }
      nlines--;
    }
    return;
  }
  i = findline(n);
  if(i < 0) {
    unsigned char j;
    if(nlines >= MAXLINES) {
      fail("full");
      return;
    }
    j = nlines;
    while(j > 0 && lineno[j - 1] > n) {
      lineno[j] = lineno[j - 1];
      {
        unsigned char k;
        for(k = 0; k < LINELEN; k++) {
          linetxt[j][k] = linetxt[j - 1][k];
        }
      }
      j--;
    }
    i = (int)j;
    nlines++;
  }
  lineno[(unsigned char)i] = n;
  {
    unsigned char k;
    for(k = 0; k < LINELEN - 1 && text[k]; k++) {
      linetxt[(unsigned char)i][k] = text[k];
    }
    linetxt[(unsigned char)i][k] = 0;
  }
}

static void
exec_stmt(void)
{
  skip();
  if(*cur == 0 || kw("rem")) {
    return;
  }
  if(kw("print") || kw("?")) {
    do_print();
    return;
  }
  if(kw("let")) {
    do_let();
    return;
  }
  if(kw("goto")) {
    if(!running) {
      fail("run");
      return;
    }
    do_goto((unsigned)expr());
    return;
  }
  if(kw("gosub")) {
    if(!running || gsp >= GOSUBMAX) {
      fail("gosub");
      return;
    }
    {
      unsigned n = (unsigned)expr();
      gchar[gsp++] = (unsigned char)(pc + 1);
      do_goto(n);
    }
    return;
  }
  if(kw("return")) {
    if(gsp == 0) {
      fail("return");
      return;
    }
    pc = gchar[--gsp];
    return;
  }
  if(kw("end") || kw("stop")) {
    running = 0;
    return;
  }
  if(kw("list")) {
    do_list();
    return;
  }
  if(kw("new")) {
    nlines = 0;
    running = 0;
    gsp = 0;
    return;
  }
  if(kw("run")) {
    if(nlines == 0) {
      return;
    }
    pc = 0;
    gsp = 0;
    running = 1;
    failed = 0;
    return;
  }
  if(kw("poke")) {
    int a, v;
    a = expr();
    skip();
    if(*cur != ',') {
      fail("poke");
      return;
    }
    cur++;
    v = expr();
    *(volatile unsigned char *)(unsigned)a = (unsigned char)v;
    return;
  }
  if(kw("if")) {
    int a, b, op;
    a = expr();
    if(!relop(&op)) {
      fail("if");
      return;
    }
    b = expr();
    if(!kw("then")) {
      fail("then");
      return;
    }
    if(reltrue(a, op, b)) {
      exec_stmt();
    }
    return;
  }
  if(kw("input")) {
    skip();
    if(!((*cur >= 'a' && *cur <= 'z') || (*cur >= 'A' && *cur <= 'Z'))) {
      fail("input");
      return;
    }
    waitvar = (unsigned char)(lower(*cur) - 'a');
    cur++;
    waiting = 1;
    running = 0;
    printf("? ");
    return;
  }
  if(kw("fre")) {
    basic_banner();
    return;
  }
  if(((*cur >= 'a' && *cur <= 'z') || (*cur >= 'A' && *cur <= 'Z')) &&
     (cur[1] == '=' || cur[1] == ' ')) {
    do_let();
    return;
  }
  fail("stmt");
}

void
basic_init(void)
{
  unsigned char i;
  nlines = 0;
  running = 0;
  waiting = 0;
  gsp = 0;
  failed = 0;
  for(i = 0; i < 26; i++) {
    vars[i] = 0;
  }
}

void
basic_banner(void)
{
  unsigned stack_bot = STACK_TOP - STACK_BYTES;
  unsigned used_end = (unsigned)basic_heaptop;
  unsigned ram_free;
  unsigned prog_cap = (unsigned)MAXLINES * (unsigned)LINELEN;
  unsigned prog_used = 0;
  unsigned char i;

  if(used_end >= stack_bot) {
    ram_free = 0;
  } else {
    ram_free = stack_bot - used_end;
  }
  for(i = 0; i < nlines; i++) {
    unsigned char k;
    for(k = 0; linetxt[i][k] != 0; k++) {
    }
    prog_used += (unsigned)k;
  }

  printf("%s %s\n", BASIC_NAME, BASIC_VER);
  printf("%u BYTES RAM  %u FREE\n", RAM_BYTES, ram_free);
  printf("PROGRAM %u/%u  BYE EXITS\n", prog_used, prog_cap);
}

int
basic_running(void)
{
  return running && !waiting;
}

void
basic_step(void)
{
  if(!running || waiting || pc >= nlines) {
    if(running && pc >= nlines) {
      running = 0;
      printf("ok\n");
    }
    return;
  }
  failed = 0;
  cur = linetxt[pc];
  {
    unsigned char here = pc;
    exec_stmt();
    if(running && !waiting && !failed && pc == here) {
      pc++;
    }
    if(running && pc >= nlines) {
      running = 0;
      printf("ok\n");
    }
  }
}

int
basic_line(char *line)
{
  cur = line;
  failed = 0;
  skip();
  if(*cur == 0) {
    return 0;
  }
  if(kw("bye")) {
    running = 0;
    waiting = 0;
    printf("monitor\n");
    return 1;
  }
  if(waiting) {
    vars[waitvar] = expr();
    waiting = 0;
    running = 1;
    pc++;
    return 0;
  }
  if(*cur >= '0' && *cur <= '9') {
    unsigned n = (unsigned)parsenum();
    store_line(n, cur);
    return 0;
  }
  exec_stmt();
  return 0;
}
