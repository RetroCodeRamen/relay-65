#include "vfs.h"

#include "uart.h"
#include <string.h>

#define NPAGE 2

/* One row per directory. Parent 0xFF = filesystem root (not listed). */
#define DIR_TABLE \
  DIR_ROW(0xFF, "/") \
  DIR_ROW(0, "/bin") \
  DIR_ROW(0, "/etc") \
  DIR_ROW(0, "/www") \
  DIR_ROW(0, "/tmp")

#define DIR_ROW(parent, path) path,
static const char *dir[] = { DIR_TABLE };
#undef DIR_ROW
#define DIR_ROW(parent, path) parent,
static const unsigned char dir_parent[] = { DIR_TABLE };
#undef DIR_ROW
#define NDIR (sizeof(dir) / sizeof(dir[0]))

/* One row per file. Parent is the NDIR index that contains it.
   Add a file here and ls/cat see it; do not keep a second listing. */
#define FILE_TABLE \
  FILE_ROW(1, "/bin/clack") \
  FILE_ROW(1, "/bin/basic") \
  FILE_ROW(1, "/bin/ed") \
  FILE_ROW(2, "/etc/motd") \
  FILE_ROW(2, "/etc/issue") \
  FILE_ROW(3, "/www/index.html") \
  FILE_ROW(4, "/tmp/notes")

#define FILE_ROW(parent, path) path,
static const char *file[] = { FILE_TABLE };
#undef FILE_ROW
#define FILE_ROW(parent, path) parent,
static const unsigned char file_parent[] = { FILE_TABLE };
#undef FILE_ROW
#define NFILE (sizeof(file) / sizeof(file[0]))

static const char *motd = "Clack on Relay-65\n";
static const char *issue = "Relay-65 Clack\n";
static const char *index_html = "<html><body><h1>Relay-65</h1><p>click-click</p></body></html>";
static char page[NPAGE][VFS_PAGE_MAX];
unsigned char cwd;
static unsigned char html_ram;

/* One ready-made listing per directory path. ls is uart_puts of that blob.
   Idle rewrites every blob from DIR_TABLE / FILE_TABLE when vfs_ls_need is set.
   Text is the real child paths, not basenames. */
#define LS_MAX 80
static char ls_root[LS_MAX] = "/bin/\n/etc/\n/www/\n/tmp/\n";
static char ls_bin[LS_MAX] = "/bin/clack\n/bin/basic\n/bin/ed\n";
static char ls_etc[LS_MAX] = "/etc/motd\n/etc/issue\n";
static char ls_www[LS_MAX] = "/www/index.html\n";
static char ls_tmp[LS_MAX] = "/tmp/notes\n";
/* Pointer table so ls is not `row * 80` (cc65 16-bit multiply). */
char *ls_blob[5] = { ls_root, ls_bin, ls_etc, ls_www, ls_tmp };
static char *ls_dst;

static unsigned char b_dir;
static unsigned char b_pos;

extern unsigned char vfs_ls_need;
extern void (*uart_idle)(void);

static int
find_dir(const char *path)
{
  unsigned char i;
  for(i = 0; i < NDIR; i++) {
    if(strcmp(dir[i], path) == 0) {
      return i;
    }
  }
  return -1;
}

static const char *
resolve(const char *path, char *out)
{
  if(path == NULL || path[0] == 0) {
    return dir[cwd];
  }
  if(path[0] == '/') {
    return path;
  }
  if(strcmp(path, "..") == 0) {
    return "/";
  }
  if(strcmp(path, ".") == 0) {
    return dir[cwd];
  }
  if(dir[cwd][0] == '/' && dir[cwd][1] == 0) {
    out[0] = '/';
    strcpy(out + 1, path);
  } else {
    strcpy(out, dir[cwd]);
    strcat(out, "/");
    strcat(out, path);
  }
  return out;
}

static int
page_slot(const char *path)
{
  if(strcmp(path, "/www/index.html") == 0) {
    return 0;
  }
  if(strcmp(path, "/tmp/notes") == 0) {
    return 1;
  }
  return -1;
}

static void
ls_putc(char c)
{
  if(b_pos < LS_MAX - 1) {
    ls_dst[b_pos++] = c;
  }
}

static void
ls_puts(const char *s)
{
  while(*s) {
    ls_putc(*s++);
  }
}

static void
ls_build_dir(unsigned char d)
{
  unsigned char i;
  ls_dst = ls_blob[d];
  b_pos = 0;
  for(i = 0; i < (unsigned char)NDIR; i++) {
    if(dir_parent[i] == d) {
      ls_puts(dir[i]);
      ls_putc('/');
      ls_putc('\n');
    }
  }
  for(i = 0; i < (unsigned char)NFILE; i++) {
    if(file_parent[i] == d) {
      ls_puts(file[i]);
      ls_putc('\n');
    }
  }
  ls_dst[b_pos] = 0;
}

void
vfs_ls_idle(void)
{
  if(!vfs_ls_need) {
    return;
  }
  ls_build_dir(b_dir);
  b_dir++;
  if(b_dir >= (unsigned char)NDIR) {
    vfs_ls_need = 0;
    b_dir = 0;
  }
}

void
vfs_ls_dirty(void)
{
  vfs_ls_need = 1;
  b_dir = 0;
}

void
vfs_ls_sync(void)
{
  while(vfs_ls_need) {
    vfs_ls_idle();
  }
}

void
vfs_init(void)
{
  cwd = 0;
  html_ram = 0;
  page[0][0] = 0;
  page[1][0] = 0;
  b_dir = 0;
  uart_idle = vfs_ls_idle;
  vfs_ls_need = 0;
}

const char *
vfs_cwd(void)
{
  return dir[cwd];
}

int
vfs_cd(const char *path)
{
  char buf[20];
  const char *p = resolve(path, buf);
  int i = find_dir(p);
  if(i < 0) {
    uart_puts("cd: no such directory\n");
    return 0;
  }
  cwd = (unsigned char)i;
  return 1;
}

void
vfs_pwd(void)
{
  uart_puts(dir[cwd]);
  uart_putc('\n');
}

void
vfs_cat(const char *path)
{
  char buf[24];
  const char *p;
  char *body;
  if(path == NULL) {
    printf("usage: cat FILE\n");
    return;
  }
  p = resolve(path, buf);
  body = vfs_file(p);
  if(body == NULL) {
    printf("cat: no such file\n");
    return;
  }
  printf("%s", body);
  if(body[0] && body[strlen(body) - 1] != '\n') {
    printf("\n");
  }
}

char *
vfs_file(const char *path)
{
  char buf[24];
  const char *p = resolve(path, buf);
  int slot;
  if(strcmp(p, "/etc/motd") == 0) {
    return (char *)motd;
  }
  if(strcmp(p, "/etc/issue") == 0) {
    return (char *)issue;
  }
  if(strcmp(p, "/bin/clack") == 0 || strcmp(p, "/bin/basic") == 0 ||
     strcmp(p, "/bin/ed") == 0) {
    return (char *)"(app)\n";
  }
  slot = page_slot(p);
  if(slot == 0 && !html_ram) {
    return (char *)index_html;
  }
  if(slot >= 0) {
    return page[slot];
  }
  return NULL;
}

unsigned
vfs_file_len(const char *path)
{
  char *s = vfs_file(path);
  unsigned n = 0;
  if(s == NULL) {
    return 0;
  }
  while(s[n]) {
    n++;
  }
  return n;
}

int
vfs_editable(const char *path)
{
  char buf[24];
  const char *p = resolve(path, buf);
  return page_slot(p) >= 0;
}

char *
vfs_edit_buf(const char *path)
{
  char buf[24];
  const char *p = resolve(path, buf);
  int slot = page_slot(p);
  unsigned i;
  if(slot < 0) {
    return NULL;
  }
  if(slot == 0 && !html_ram) {
    for(i = 0; index_html[i] && i < VFS_PAGE_MAX - 1; i++) {
      page[0][i] = index_html[i];
    }
    page[0][i] = 0;
    html_ram = 1;
  }
  return page[slot];
}
