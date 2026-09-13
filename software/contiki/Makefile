# Clack — Relay-65 shell on Contiki (no process_run on this path).

ROOT := $(abspath ../..)
CONTIKI := $(ROOT)/contiki
TARGET = relay65
CONTIKI_WITH_IPV6 = 0
RELSTR = relay65
CONTIKI_PROJECT = console
PROJECT_SOURCEFILES += basic.c vfs.c man.c edit.c uart.c
CFLAGS += -DRELAY65_WITH_BASIC -I$(ROOT)/software/contiki

.DEFAULT_GOAL := bin

all: $(CONTIKI_PROJECT)

include $(CONTIKI)/Makefile.include

$(OBJECTDIR)/ls.o: ls.s | $(OBJECTDIR)
	$(AS) $(ASFLAGS) -o $@ $<

console.relay65: console.co $(PROJECT_OBJECTFILES) $(OBJECTDIR)/ls.o \
		contiki-$(TARGET).a $(OBJECTDIR)/crt0.o $(OBJECTDIR)/write.o
	$(CC65_HOME)/bin/ld65 -C $(RELAY65_CFG) -o $@ \
	  $(OBJECTDIR)/crt0.o $(OBJECTDIR)/write.o console.co \
	  $(PROJECT_OBJECTFILES) $(OBJECTDIR)/ls.o contiki-$(TARGET).a \
	  $(CC65_HOME)/lib/none.lib

bin: $(CONTIKI_PROJECT)
	cp -f console.relay65 console.bin

.PHONY: bin

.PHONY: hello run
hello:
	$(MAKE) -C "$(CONTIKI)/examples/hello-world" \
		TARGET=relay65 CONTIKI_WITH_IPV6=0 CONTIKI="$(CONTIKI)" RELSTR=relay65
	cp "$(CONTIKI)/examples/hello-world/hello-world.relay65" hello-world.bin

run: console.bin
	cd $(ROOT) && ./relay65 --gui --overclock --run --load software/contiki/console.bin
