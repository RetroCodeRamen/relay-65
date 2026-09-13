# Relay-65 emulator

Python model of the **relay CPU**, not a shortcut 6502 interpreter.

Each 6502 instruction is a list of micro-ops on **one 8-bit bus** through **one ALU**. Packed EEPROM rows (`CW`) are the control card. Modules in `relay65/` are the cards.

Project overview, downloads, and Clack: **[README.md](../README.md)**. Frozen Windows/Linux apps: **[pack/README.md](../pack/README.md)**. Hardware contract: **[docs/RELAY-CPU.md](../docs/RELAY-CPU.md)**. Coil times: **[docs/TIMING.md](../docs/TIMING.md)**.

`--gui` is a native window (tkinter) with the same layout as the browser panel: serial, CLOCK / MEMORY, HOST / REAL / WARP, MACHINE | 6502. If tkinter is missing, the GUI is `http://127.0.0.1:8065`.

## Run

From the **repo root** (`./relay65` puts `emulator/` on `PYTHONPATH`). Python 3.9+.

```bash
python3 -m unittest discover -s emulator/tests -v
./relay65 --program emulator/programs/hello.s --max 200
./relay65 --overclock --load software/images/console.bin --gui --run
./relay65
```

Windows checkout (python.org Python):

```text
py -3 relay65 --gui --overclock --run --load software/images/console.bin
```

From this directory:

```bash
python3 -m unittest discover -s tests -v
python3 -m relay65 --program programs/hello.s --max 200
python3 -m relay65
```

The last command boots the monitor ROM at `$E000`. Type on the host keyboard; that is the UART at `$C000`. Ctrl-C is front-panel HALT. Headless stdin UART is POSIX (`select`); use `--gui` on Windows.

`software/images/console.bin` is the v1.0.0 Clack image (Contiki 3.x, ClackShell 1.0). Rebuild with `make -C software/contiki` (needs the `contiki` tree and cc65).

## Lamps and two consoles

**Serial** is the Teletype. **Lamps** are two banks: MACHINE (MAR / bus / IR / sequencer) and 6502 (A X Y SP P PC).

`*` = lamp on, `.` = lamp off. MAR is the address register (not always the live fetch address). BUS is the last internal-bus byte. IR is the opcode.

```bash
# lamps + serial, relay-timed clock (~20 ms/microstep)
./relay65 --gui --load software/images/console.bin
# click RUN. SPEED cycles RELAY (coils) → 1s=1min (60×) → WARP (host max).
# HOST / REAL / WARP: PC time vs how long those rows would take on relays.
# STEP ROW = one EEPROM word. STEP OP = one 6502 instruction.

./relay65 --gui --overclock --run --load software/images/console.bin
```

`--panel` is a text front panel; serial is TCP (`nc 127.0.0.1 6502` by default). Not Windows (needs termios).

Panel keys: `A`+hex address, `D`+hex data, `E` examine, `N` next, `P` deposit, `O` deposit next, `R` run, `S` stop, space = STEP ROW, `K` = STEP OP, `T` speed, `I` reset, `Q` quit.

`--trace` prints register/IR/MAR/microstep state. `--dump-microcode` writes packed FETCH/RESET/IRQ/NMI/execute images. `--leds` prints `*` / `.` lamps on stderr.

## What is intentionally slow

Opcode/operand fetch is Design B: ADDR_PC plus a dedicated PC+1, packed into one EEPROM row (Φ2 loads IR/MDR and PC together). Stack uses ADDR_SP; INX/Y and SP±1 use an 8-bit incrementer. Indexed addressing still shares the one 8-bit ALU. Software-visible PC, memory, and flags stay the same.

On that clock, Clack boots in **1 min 55 s** and the first `ls` takes **38 s** ([docs/TIMING.md](../docs/TIMING.md)). `--overclock` is for the host PC, not a faster relay machine.

## Memory map (v0.1)

Same decode as the Memory/System card. Full table in the [root README](../README.md). Short version:

- `$0000–$BFFF` / `$D000+` SRAM (512 KiB physical, paged)
- `$C000–$C002` UART
- `$C010` bank, `$C016` ROM overlay, `$C017` CF autoboot, `$C018–$C01B` pages
- `$C020–$C023` tick/IRQ
- `$C100` CompactFlash, `$C200` ESP32 mailbox
- `$E000–$FFFF` ROM overlay while `$C016` bit0=1 (write-through to SRAM)
