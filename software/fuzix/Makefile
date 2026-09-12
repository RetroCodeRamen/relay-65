# Relay-65 FUZIX kernel (cc65).
ROOT := $(abspath $(CURDIR)/../..)
FUZIX := $(ROOT)/fuzix
CC65_HOME := $(ROOT)/third_party/cc65
include $(FUZIX)/version.mk
# Empty SUBVERSION is dropped by make and makeversion wants 3 args.
SUBVERSION := 0
export CC65_HOME VERSION SUBVERSION
export PATH := $(CC65_HOME)/bin:$(PATH)

.PHONY: kernel cf clean

kernel:
	$(MAKE) -C "$(FUZIX)/Kernel" TARGET=relay65 ROOT_DIR="$(abspath $(ROOT)/fuzix/Kernel)"

cf: kernel
	python3 "$(CURDIR)/pack-cf.py" "$(FUZIX)/Kernel/fuzix.bin" "$(ROOT)/Images/relay65/cf.img"

clean:
	$(MAKE) -C "$(FUZIX)/Kernel" TARGET=relay65 ROOT_DIR="$(abspath $(ROOT)/fuzix/Kernel)" clean
