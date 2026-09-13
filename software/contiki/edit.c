#include "edit.h"
#include "vfs.h"

#include "uart.h"
#include <string.h>

static unsigned char on;
static unsigned char started;
static unsigned pos;
static char *page;
static char pathstore[20];

void
edit_start(const char *path)
{
  if(path == NULL || path[0] == 0) {
    path = "/tmp/notes";
  }
  page = vfs_edit_buf(path);
  if(page == NULL) {
    printf("edit: %s not editable\n", path == NULL ? "?" : path);
    on = 0;
    return;
  }
  {
    unsigned i;
    for(i = 0; i < sizeof(pathstore) - 1 && path[i]; i++) {
      pathstore[i] = path[i];
    }
    pathstore[i] = 0;
  }
  on = 1;
  started = 0;
  pos = 0;
  printf("edit %s\n", pathstore);
  if(page[0]) {
    printf("%s", page);
    if(page[strlen(page) - 1] != '\n') {
      printf("\n");
    }
  }
  printf(". ends  (first line replaces the file)\n");
}

int
edit_active(void)
{
  return on;
}

int
edit_line(const char *line)
{
  unsigned n, i;
  if(!on) {
    return 0;
  }
  if(line[0] == '.' && line[1] == 0) {
    on = 0;
    printf("saved %u bytes\n", pos ? pos : vfs_file_len(pathstore));
    return 0;
  }
  if(!started) {
    started = 1;
    pos = 0;
    page[0] = 0;
  }
  n = 0;
  while(line[n]) {
    n++;
  }
  if(pos && pos < VFS_PAGE_MAX - 1) {
    page[pos++] = '\n';
  }
  if(pos + n >= VFS_PAGE_MAX) {
    printf("full\n");
    on = 0;
    page[pos] = 0;
    return 0;
  }
  for(i = 0; i < n; i++) {
    page[pos++] = line[i];
  }
  page[pos] = 0;
  return 1;
}
