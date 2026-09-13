#ifndef RELAY65_VFS_H_
#define RELAY65_VFS_H_

#define VFS_PAGE_MAX 192

void vfs_init(void);
void vfs_ls_idle(void);
void vfs_ls_dirty(void);
void vfs_ls_sync(void);
const char *vfs_cwd(void);
int vfs_cd(const char *path);
void vfs_ls(const char *path);
void vfs_pwd(void);
void vfs_cat(const char *path);
char *vfs_file(const char *path);
unsigned vfs_file_len(const char *path);
int vfs_editable(const char *path);
char *vfs_edit_buf(const char *path);

#endif
