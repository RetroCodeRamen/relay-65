# Stay-up Contiki console (etimer + UART line input).

ROOT := $(abspath ../..)
CONTIKI := $(ROOT)/contiki
TARGET = relay65
CONTIKI_WITH_IPV6 = 0
RELSTR = relay65
CONTIKI_PROJECT = console
PROJECT_SOURCEFILES += basic.c
CFLAGS += -DRELAY65_WITH_BASIC -I$(ROOT)/software/contiki

.DEFAULT_GOAL := bin

all: $(CONTIKI_PROJECT)

include $(CONTIKI)/Makefile.include

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
