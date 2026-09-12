
CSRCS = devtty.c
CSRCS += devices.c main.c esp32nic.c

ASRCS = relay65.s crt0.s
ASRCS += tricks.s commonmem.s

DSRCS = ../../dev/devide.c ../../dev/blkdev.c
DISCARD_DSRCS = ../../dev/mbr.c ../../dev/devide_discard.c

COBJS = $(CSRCS:.c=$(BINEXT))
AOBJS = $(ASRCS:.s=$(BINEXT))
DOBJS = $(patsubst ../../dev/%.c,%.o, $(DSRCS))
DISCARD_DOBJS = $(patsubst ../../dev/%.c,%.o, $(DISCARD_DSRCS))

OBJS  = $(COBJS) $(AOBJS) $(DOBJS) $(DISCARD_DOBJS)

CROSS_CCOPTS += -I../../dev/

all:	$(OBJS)

$(COBJS): %$(BINEXT): %.c
	$(CROSS_CC) $(CROSS_CCOPTS) $(CROSS_CC_SEG1) $<

$(AOBJS): %$(BINEXT): %.s
	$(CROSS_AS) $(ASOPTS) $< -o $*$(BINEXT)

$(DOBJS): %$(BINEXT): ../../dev/%.c
	$(CROSS_CC) $(CROSS_CCOPTS) $(CROSS_CC_SEG1) -c $<
	mv ../../dev/$*.o .

$(DISCARD_DOBJS): %$(BINEXT): ../../dev/%.c
	$(CROSS_CC) $(CROSS_CCOPTS) $(CROSS_CC_SEGDISC) -c $<
	mv ../../dev/$*.o .

clean:
	rm -f $(OBJS) *.o core *~ fuzix.img fuzix.bin

image:
	ld65 -o ../../fuzix.bin -C ld65.cfg -m ../../fuzix.map crt0.o commonmem.o \
	relay65.o ../../start.o ../../version.o ../../cpu-6502/lowlevel-6502.o \
	tricks.o main.o ../../timer.o ../../kdata.o devices.o \
	blkdev.o mbr.o devide.o devide_discard.o ../../mm/memalloc_none.o \
	../../devio.o ../../filesys.o ../../process.o ../../inode.o ../../syscall_fs.o \
	../../syscall_proc.o ../../syscall_other.o ../../mm.o ../../mm/bankfixed.o \
	../../tty.o ../../devsys.o ../../syscall_fs2.o ../../syscall_fs3.o \
	../../syscall_exec16.o ../../syscall_exec.o ../../blk512.o \
	../../usermem.o ../../cpu-6502/usermem_std-6502.o devtty.o esp32nic.o \
	$(CC65_HOME)/lib/none.lib

IMAGES = $(FUZIX_ROOT)/Images/$(TARGET)

diskimage: image
	mkdir -p $(IMAGES)
	dd if=$(FUZIX_ROOT)/Standalone/filesystem-src/parttab.40M of=$(IMAGES)/disk.img bs=40017920 conv=sync
	dd if=$(IMAGES)/filesys.img of=$(IMAGES)/disk.img bs=512 seek=2048 conv=notrunc
	dd if=../../fuzix.bin of=$(IMAGES)/disk.img bs=512 seek=1 conv=notrunc
