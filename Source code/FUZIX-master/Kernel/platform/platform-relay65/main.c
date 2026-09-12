#include <kernel.h>
#include <timer.h>
#include <kdata.h>
#include <printf.h>
#include <blkdev.h>
#include <devide.h>
#include <devtty.h>
#include <esp32nic.h>

uint8_t kernel_flag = 1;
uint16_t swap_dev = 0xFFFF;

#define TICK_LO		((volatile uint8_t *)0xC020)
#define TICK_HI		((volatile uint8_t *)0xC021)
#define TICK_CTRL	((volatile uint8_t *)0xC022)
#define TICK_IFR	((volatile uint8_t *)0xC023)

void plt_idle(void)
{
    irqflags_t flags = di();
    tty_poll();
    esp32_poll();
    irqrestore(flags);
}

void do_beep(void)
{
}

void pagemap_init(void)
{
    int i;
    /* Kernel is pages 0–3. User maps of four 16K pages; 4 must be last (init). */
    for (i = 6; i >= 0; i--)
        pagemap_add(4 + i * 4);
}

void map_init(void)
{
}

uint8_t plt_param(char *p)
{
    return 0;
}

void device_init(void)
{
#ifdef CONFIG_IDE
	devide_init();
#endif
	esp32_init();
	*TICK_CTRL = 1;
}

void plt_interrupt(void)
{
	tty_poll();
	esp32_poll();
	if (*TICK_IFR & 0x80) {
		*TICK_IFR = 0x80;
		timer_interrupt();
	}
}

extern uint8_t hd_map;
extern void hd_read_data(uint8_t *p);
extern void hd_write_data(uint8_t *p);

void devide_read_data(void)
{
	if (blk_op.is_user)
		hd_map = 1;
	else
		hd_map = 0;
	hd_read_data(blk_op.addr);	
}

void devide_write_data(void)
{
	if (blk_op.is_user)
		hd_map = 1;
	else
		hd_map = 0;
	hd_write_data(blk_op.addr);	
}
