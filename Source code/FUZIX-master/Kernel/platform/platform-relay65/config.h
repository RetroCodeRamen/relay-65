/* Enable to make ^Z dump the inode table for debug */
#undef CONFIG_IDUMP
/* Enable to make ^A drop back into the monitor */
#undef CONFIG_MONITOR
/* Profil syscall support (not yet complete) */
#undef CONFIG_PROFIL
/* Acct syscall support */
#undef CONFIG_ACCT
/* Multiple processes in memory at once */
#define CONFIG_MULTI
/* Use fixed banks for now. It's simplest and we've got so much memory ! */
#define CONFIG_BANKS	1
/* Permit large I/O requests to bypass cache and go direct to userspace */
#define CONFIG_LARGE_IO_DIRECT(x)	1

#define CONFIG_CALL_R2L		/* Runtime stacks arguments backwards */

/*
 *	Relay-65: 512K SRAM, four 16K page registers at $C018–$C01B.
 *	Kernel pages 0–3, seven user maps of four pages (4–31).
 */
#define CONFIG_BANK_FIXED
#define MAX_MAPS 	7   /* 7 x 64K user maps */
#define MAP_SIZE    0xDE00

#define TICKSPERSEC 100	    /* Ticks per second */

/* We've not yet made the rest of the code - eg tricks match this ! */
#define MAPBASE	    0x0000  /* We map from 0 */
#define PROGBASE    0x2000  /* also data base */
#define PROGLOAD    0x2000
#define PROGTOP     0xFE00

#define CONFIG_IDE
#define IDE_DRIVE_COUNT 1
#define MAX_BLKDEV 1

/* FIXME: swap */

#define BOOT_TTY 513        /* Set this to default device for stdio, stderr */

/* We need a tidier way to do this from the loader */
#define CMDLINE	NULL	  /* Location of root dev name */

/* Device parameters */
#define NUM_DEV_TTY 1
#define TTYDEV   BOOT_TTY /* Device used by kernel for messages, panics */
#define NBUFS    5        /* Number of block buffers */
#define NMOUNTS	 2	  /* Number of mounts at a time */

#define plt_discard()
#define plt_copyright()

#define BOOTDEVICENAMES "hd#"

#define CONFIG_SMALL

/* TCP/IP is on the ESP32 card ($C200), not in this kernel. */
