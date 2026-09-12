# cc65 target for the Relay-65 memory map (UART $C000, RAM $0200-$7FFF).
# Requires third_party/cc65 to be built.

CC65_HOME ?= $(abspath ../../third_party/cc65)
CC        := $(CC65_HOME)/bin/cl65
ASMINC    := $(CC65_HOME)/asminc

CFLAGS := -t none -O --cpu 6502
LDFLAGS := -t none -C relay65.cfg -Wl -D,__STACKSTART__=$$8000

hello.bin: hello.c crt0.s write.s relay65.cfg
	CC65_HOME=$(CC65_HOME) $(CC) -t none -O --cpu 6502 --start-addr 0x0200 \
		--asm-include-dir $(ASMINC) \
		-C relay65.cfg -o $@ crt0.s write.s hello.c

clean:
	rm -f hello.bin hello.o crt0.o write.o
