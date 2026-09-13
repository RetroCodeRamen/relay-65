#include "man.h"

#include "uart.h"

static char
lower(char c)
{
  if(c >= 'A' && c <= 'Z') {
    return (char)(c + 32);
  }
  return c;
}

static int
same(const char *a, const char *b)
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

void
man_list(void)
{
  uart_puts("topics: clack help ls cd pwd cat echo edit man basic fs\n"
            "        time peek poke io bank watch\n"
            "        clear uname free hd\n"
            "man TOPIC\n");
}

void
man_show(const char *topic)
{
  if(topic == NULL || same(topic, "help")) {
    uart_puts("HELP\n"
              "  Clack overview. Type help for the short list.\n"
              "  ls /bin - programs.  man NAME - this text.\n");
    return;
  }
  if(same(topic, "clack") || same(topic, "shell")) {
    uart_puts("CLACK\n"
              "  The Relay-65 shell. Contiki is the OS; Clack is what you type at.\n"
              "  Prompt is _>  (cwd prefix when you leave /).\n"
              "  Programs: /bin/clack  /bin/basic  /bin/ed\n");
    return;
  }
  if(same(topic, "ls")) {
    uart_puts("LS [DIR]\n"
              "  Print the cached listing for that directory.\n"
              "  Paths: /  /bin  /etc  /www  /tmp\n");
    return;
  }
  if(same(topic, "cd")) {
    printf("CD [DIR]\n");
    printf("  Change directory.  cd ..  goes to /.\n");
    printf("  Dirs: /  /bin  /etc  /www  /tmp\n");
    return;
  }
  if(same(topic, "pwd")) {
    printf("PWD\n");
    printf("  Print the current directory.\n");
    return;
  }
  if(same(topic, "cat")) {
    printf("CAT FILE\n");
    printf("  Print a file.  cat motd  from /etc works after cd etc.\n");
    return;
  }
  if(same(topic, "echo")) {
    printf("ECHO TEXT\n");
    printf("  Print the rest of the line.\n");
    return;
  }
  if(same(topic, "edit") || same(topic, "ed")) {
    printf("EDIT [FILE]    (also: ed)\n");
    printf("  Line editor for RAM files.\n");
    printf("  Default /tmp/notes. Also /www/index.html.\n");
    printf("  Type lines. A lone . saves and exits.\n");
    printf("  First real line replaces the file; later lines append.\n");
    return;
  }
  if(same(topic, "man")) {
    printf("MAN [TOPIC]\n");
    printf("  Short manual. No topic lists names.\n");
    return;
  }
  if(same(topic, "fs") || same(topic, "vfs")) {
    printf("FS\n");
    printf("  RAM directories, not a disk.\n");
    printf("  /  /bin  /etc  /www  /tmp\n");
    printf("  Programs: /bin/clack  /bin/basic  /bin/ed\n");
    printf("  Editable: /tmp/notes  /www/index.html\n");
    return;
  }
  if(same(topic, "basic")) {
    printf("BASIC\n");
    printf("  Integer Tiny BASIC. Start with:  basic\n");
    printf("  Leave with:  BYE\n");
    printf("  Immediate: PRINT  LET  LIST  NEW  RUN  FRE\n");
    printf("             PEEK()  POKE a,v  INPUT  REM\n");
    printf("  Program: numbered lines, 24 x 40 chars, A-Z integers.\n");
    printf("  No FOR, no strings, no files. Hex with $.\n");
    printf("  In a running program: GOTO GOSUB RETURN IF THEN END STOP\n");
    return;
  }
  if(same(topic, "time")) {
    printf("TIME\n");
    printf("  Contiki clock and $C020 tick counter.\n");
    return;
  }
  if(same(topic, "peek")) {
    printf("PEEK ADDR [N]\n");
    printf("  Dump up to 16 bytes. Hex ADDR, optional $.\n");
    printf("  Avoid zeropage - cc65 lives there.\n");
    return;
  }
  if(same(topic, "poke")) {
    printf("POKE ADDR BYTES..\n");
    printf("  Write hex bytes at ADDR.\n");
    return;
  }
  if(same(topic, "io")) {
    printf("IO\n");
    printf("  UART $C001, bank $C010, tick ctrl/IFR.\n");
    return;
  }
  if(same(topic, "bank")) {
    printf("BANK [NN]\n");
    printf("  Read or write the $C010 window latch.\n");
    return;
  }
  if(same(topic, "watch")) {
    printf("WATCH [on|off]\n");
    printf("  Print [clock N] once per second. Off by default.\n");
    return;
  }
  if(same(topic, "clear")) {
    printf("CLEAR\n");
    printf("  Scroll the teletype. Does not wipe RAM.\n");
    return;
  }
  if(same(topic, "uname")) {
    uart_puts("UNAME\n"
              "  Machine, OS, and shell: Relay-65 Contiki Clack.\n");
    return;
  }
  if(same(topic, "free")) {
    printf("FREE\n");
    printf("  Bytes of RAM still below the C stack.\n");
    return;
  }
  if(same(topic, "hd")) {
    printf("HD ADDR [N]\n");
    printf("  Same as peek - hex dump memory.\n");
    return;
  }
  printf("man: no page for %s\n", topic);
  man_list();
}
