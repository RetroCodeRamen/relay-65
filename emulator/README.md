# Relay-65 emulator

Python model of the **relay CPU**, not a shortcut 6502 interpreter.

Each 6502 instruction is a list of micro-ops on **one 8-bit bus** through **one ALU**. Packed EEPROM rows (`CW`) are the control card. Modules in `relay65/` are the cards.

Project overview, memory map, and how to run Contiki/BASIC/FUZIX: **[README.md](../README.md)**. Hardware contract: **[docs/RELAY-CPU.md](../docs/RELAY-CPU.md)**. Physical Design B (PC+1, relay bus OE) is specified in **[RELAY65_HARDWARE_IMPLEMENTATION.md](../RELAY65_HARDWARE_IMPLEMENTATION.md)** and is **not** substituted in this microcode yet.

## Run

From the **repo root** (`./relay65` puts `emulator/` on `PYTHONPATH`):

```bash
python3 -m unittest discover -s emulator/tests -v
./relay65 --program emulator/programs/hello.s --max 200
./relay65 --overclock --load software/cc65/hello.bin --max 400000
./relay65
```

From this directory:

```bash
python3 -m unittest discover -s tests -v
python3 -m relay65 --program programs/hello.s --max 200
python3 -m relay65
```

The last command boots the monitor ROM at `$E000`. Type on the host keyboard; that is the UART at `$C000`. Ctrl-C is front-panel HALT.

## Lamps and two consoles

**Serial** is the Teletype. **Lamps/switches** are the front panel.

`*` = lamp on, `.` = lamp off. ADDR is MAR (A[15:0]), DATA is the last bus byte, IR is the instruction register.

```bash
# lamps + serial, relay-timed clock (~20 ms/microstep)
./relay65 --gui --load software/cc65/hello.bin
# click RUN. OVERCLOCK = host max speed.

./relay65 --gui --overclock --run --load software/contiki/hello-world.bin
```

If tkinter is missing, the GUI is the browser at `http://127.0.0.1:8065` (green SERIAL box). UART is also copied to the launching terminal.

`--panel` is a text front panel; serial is TCP (`nc 127.0.0.1 6502` by default).

Panel keys: `A`+hex EXAMINE address, `D`+hex data, `E` examine, `P` deposit, `R` run, `S` stop, space = step, `I` reset.

`--trace` prints register/IR/MAR/microstep state. `--dump-microcode` writes packed FETCH/RESET/IRQ/NMI/execute images. `--leds` prints Altair-style lamps on stderr.

Build Contiki with `make -C software/contiki` (needs the `contiki` tree and cc65). That uses the `relay65` platform and the same UART as cc65.

## What is intentionally slow

Program-counter increment on fetch is a **dedicated 16-bit +1** (`CW.pc_inc`).
Opcode/operand reads put **PC** on A[15:0] (`CW.addr_pc`). FETCH is 2 microsteps;
`fetch_byte` is 2. Indexed addressing, SP±1, and ADC still share the 8-bit ALU.

A later fused ALU→register writeback is optional Design C, not in this microcode.

## Memory map (v0.1)

Same decode as the Memory/System card. Full table in the [root README](../README.md). Short version:

- `$0000–$BFFF` / `$D000+` SRAM (512 KiB physical, paged)
- `$C000–$C002` UART
- `$C010` bank, `$C016` ROM overlay, `$C017` CF autoboot, `$C018–$C01B` pages
- `$C020–$C023` tick/IRQ
- `$C100` CompactFlash, `$C200` ESP32 mailbox
- `$E000–$FFFF` ROM overlay while `$C016` bit0=1 (write-through to SRAM)
