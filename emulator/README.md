# Relay-65 emulator

Python model of the **relay CPU**, not a shortcut 6502 interpreter.

Each 6502 instruction is a list of micro-ops that move bytes on **one 8-bit
bus** through **one ALU**. That is the same reuse the hardware will use
(microcode in EEPROM, coil drivers on those control lines).

Read **[docs/RELAY-CPU.md](../docs/RELAY-CPU.md)** before soldering. The
modules in `relay65/` are the cards.

## Run

```bash
cd emulator
python3 -m unittest discover -s tests -v
python3 -m relay65 --program programs/hello.s --max 200
python3 -m relay65 --load ../software/cc65/hello.bin --max 400000
python3 -m relay65
```

## Lamps and two consoles

Same split as the hardware: **serial** is the Teletype; **lamps/switches** are the
front panel.

`*` = lamp on, `.` = lamp off. ADDR is MAR (A[15:0]), DATA is the last bus
byte, IR is the instruction register.

```bash
# from the Relay-65 repo root — lamps/switches + serial, relay-timed clock
./relay65 --gui --load software/cc65/hello.bin
# click RUN. OVERCLOCK = host max speed. Default is ~20 ms per microstep
# (10 ms Φ0 release + 10 ms Φ1 operate).

./relay65 --gui --overclock --run --load software/contiki/hello-world.bin
```

Contiki hello-world is `make -C software/contiki`. That uses the `relay65` platform and the same UART as cc65.

Panel keys: `A`+hex EXAMINE address, `D`+hex data, `E` examine, `P` deposit,
`R` run, `S` stop, space = step, `I` reset.

The last command boots the monitor ROM at `$E000`. Type on the host
keyboard; it is the UART at `$C000`. Ctrl-C is the front-panel HALT pin.

`--trace` prints register/IR/MAR/microstep state (front-panel lights).

## What is intentionally slow

Program-counter increment, stack pointer update, and indexed addressing all
share the 8-bit adder. A fetch is many relay cycles. That is not a bug; it is
the machine. A later dedicated PC+1 is a microcode swap, not a firmware change.

## Memory map (v0.1)

Same decode as the Memory/System card. See the blueprint doc for banks and slots.

- `$0000–$7FFF` RAM
- `$8000–$BFFF` banked RAM window (`$C010`)
- `$C000` UART data, `$C001` status
- `$E000–$FFFF` ROM (vectors at `$FFFA`)
