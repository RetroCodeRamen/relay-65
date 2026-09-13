# Relay-65

A **luggable electromechanical 6502**: software-visible NMOS 6502 because a **relay datapath** executes it. Semiconductors are allowed for SRAM/ROM, microcode EEPROM, coil drivers, clocks, UART, CompactFlash, and an ESP32 network card. A hidden MCU that interprets opcodes is not the machine.

The Python emulator under `emulator/` is the **behavioral reference**. Contiki (with integer BASIC), the monitor ROM, and a FUZIX kernel port already run on it. Physical hardware is designed, not built.

## Status

| Layer | State |
| --- | --- |
| ISA / binaries | Official NMOS 6502; illegal opcodes jam. cc65 `--cpu 6502` only (no 65C02). |
| Emulator | Microcoded 8-bit bus, one ALU, packed EEPROM control words. Design B fetch is ADDR_PC + hardware PC+1 in **one** µstep per opcode/operand byte. Stack uses ADDR_SP; INX/Y/SP use an 8-bit +1/−1 helper. Indexed EA still uses the ALU. |
| Software | Monitor at `$E000`. Contiki console + BASIC. FUZIX kernel bring-up (CF boot, not a finished Unix box). TCP stays on the ESP32 mailbox, not uIP on the 6502. |
| Hardware v1 | **Design B** is in the emulator: ADDR_PC, hardware PC+1, ADDR_SP, 8-bit ±1, packed fetch. Physical boards are not built. Envelope **~450 DPDT** (populated a bit above the old 315–360 once stack/INX helpers are counted). |

## Design rules

1. The emulator is the hardware contract. If the emulator does it, the relay CPU does it.
2. Relays hold and route CPU data and perform ALU work. Silicon sequences coils and stores memory.
3. Spend relays on fetch, stack, and INX/Y — they run on every hot path. Do not duplicate the ALU to go faster.
4. Prefer real speed, an electromechanical datapath, and a buildable relay count over a 220-relay silicon-bus minimum.

Philosophy and card-cage intent: [DESIGN.md](DESIGN.md). Frozen emulator/hardware contract: [docs/RELAY-CPU.md](docs/RELAY-CPU.md). OS map: [docs/OS-BRINGUP.md](docs/OS-BRINGUP.md). Coil times: [docs/TIMING.md](docs/TIMING.md).

## Quick start

Python 3. No extra packages for the core emulator. `--gui` uses tkinter (same
front panel as the browser UI), or a browser panel at `http://127.0.0.1:8065`
if tkinter is missing.

**Download (Windows / Linux):** GitHub Actions builds `Relay-65.exe` and
`Relay-65`. Double-click: Clack loads, warp clock, RUN. Type in the serial
pane. Rebuild those binaries with `pyinstaller pack/relay65.spec` (needs
`software/images/console.bin`).

```bash
# tests
cd emulator && python3 -m unittest discover -s tests -v

# from repo root — monitor ROM, UART on stdin/stdout
./relay65 --overclock --max 20000

# front panel (lamps + serial). START is STOP unless --run
./relay65 --gui --overclock --run --load software/images/console.bin
```

Windows (from a checkout, Python from python.org):

```text
py -3 relay65 --gui --overclock --run --load software/images/console.bin
```

`--overclock` skips millisecond coil waits (needed to use Contiki/BASIC on a PC). Default timing is ~20 ms per microstep. `--minute` (or SPEED on the panel) runs 60×: one PC second = one minute of relay time.

Panel: `R` run, `S` stop, space step, `I` reset, `A`+hex examine address, `D`+hex data, `E` examine, `P` deposit. Serial is the Teletype (`$C000`); lamps are the front panel.

## Repository layout

| Path | What |
| --- | --- |
| `./relay65` | Run the emulator from the repo root |
| `pack/` | PyInstaller spec for Windows/Linux desktop binaries |
| `software/images/` | Shipped Clack image (`console.bin`) for downloads |
| `emulator/` | CPU, ALU, memory, UART, CF, ESP32 mailbox, panel/GUI |
| `emulator/rom/monitor.s` | Front-panel monitor (assembled at run time) |
| `software/cc65/` | Bare-metal crt0, UART write, `relay65.cfg` |
| `software/contiki/` | Console + BASIC; builds against the `contiki` tree |
| `software/fuzix/` | CF pack helper; kernel is `fuzix/Kernel/platform/platform-relay65/` |
| `docs/` | CPU contract, OS bring-up |
| `RELAY65_HARDWARE_IMPLEMENTATION.md` | Reverse-engineered emulator + physical Design A/B/C |
| `video-assets/` | Intro script and related media notes |
| `contiki`, `fuzix` | Symlinks to local upstream checkouts (`Source code/…`, gitignored) |
| `third_party/cc65` | Local cc65 (gitignored toolchain) |

Upstream Contiki/FUZIX/cc65 are **not** in git. Clone or unpack them locally so the `contiki` and `fuzix` symlinks and `third_party/cc65/bin/cl65` resolve, then build:

```bash
make -C software/cc65
make -C software/contiki hello          # hello-world.bin
make -C software/contiki                # console.bin + BASIC (also software/images/console.bin)
make -C software/fuzix kernel           # needs cl65 on PATH
```

## Memory map (v0.1)

Visible 64 KiB 6502 space; **512 KiB** physical SRAM (32 × 16 KiB pages).

| Range | Function |
| --- | --- |
| `$0000–$7FFF` | RAM (page registers can remap) |
| `$8000–$BFFF` | Banked window (`$C010`) / page 2 |
| `$C000–$C002` | UART data / status / control |
| `$C010` | Contiki bank latch |
| `$C016` | ROM overlay enable (reads EEPROM; **writes write-through SRAM**) |
| `$C017` | Autoboot jumper (CF LBA 1) |
| `$C018–$C01B` | Four 16 KiB page registers |
| `$C020–$C023` | Tick counter + IRQ enable/IFR |
| `$C100` | CompactFlash (8-bit IDE), slot 0 |
| `$C200` | ESP32 mailbox (TCP on the ESP32) |
| `$C300+` | SRAM (not I/O in v0.1) |
| `$E000–$FFFF` | ROM overlay when `$C016` bit0=1; vectors `$FFFA` |

C programs load at `$0200`. IRQ/NMI ROM vectors `JMP ($00F0)` / `JMP ($00F2)`. Drop the ROM overlay from a RAM trampoline (e.g. `$0100`), not while PC is in `$E000`.

## Software on the machine

**Monitor** — dump/deposit/go, `f` CF boot. RESET always hits ROM; `--fuzix` inserts CF + jumper, it does not poke PC.

**Contiki** — no IPv6/uIP on the 6502. Daily OS. The shell is **Clack** (`help`, `ls`, `man`, `edit`, `basic`). Type in the GUI serial pane. On the 20 ms coil clock, boot to `_>` is **1 min 55 s**; first `ls` is **38 s**. See [docs/TIMING.md](docs/TIMING.md).

**BASIC** — integer Tiny BASIC subset started from Clack (`PRINT`, `LET`, `RUN`, `PEEK`/`POKE`, `BYE`).

**FUZIX** — NMOS 6502 platform; kernel can sign on and wait at `bootdev:`. Root filesystem / `/init` are still bring-up work. See `fuzix/Kernel/platform/platform-relay65/README.md`.

```bash
./relay65 --gui --overclock --run --load software/images/console.bin
./relay65 --gui --overclock --run --fuzix fuzix/Kernel/fuzix.bin
```

Profile microstep mix (does not change CPU behavior):

```bash
PYTHONPATH=emulator python3 emulator/tools/profile_workloads.py
```

## Hardware direction

The emulator **is** Design B microcode: packed ADDR_PC + PC+1 fetch, ADDR_SP,
8-bit ±1 for INX/Y/SP, ALU A-from-bus on taken branches. Software-visible
6502 results did not change. Physical boards still need the bit-cell and
contact-carry bench experiments in [RELAY65_HARDWARE_IMPLEMENTATION.md](RELAY65_HARDWARE_IMPLEMENTATION.md).

Still ahead of the solder (not missing in the emulator):

- 1 DPDT per stored bit (hold + MOSFET LOAD), **if** the bit-cell experiment passes
- Relay output-enable onto the internal bus (4 DPDT per 8-bit source)
- Contact-mode carry (not eight sequential coil ripples)
- Variable microcycle classes so ADD does not slow every transfer
- **One** ALU; no second adder

The old “do not retarget microcode until experiments pass” line is obsolete.
The control store already matches the intended boards. Changing packing later
is still a microcode substitution software cannot see.

## Documentation

| Doc | Use |
| --- | --- |
| [DESIGN.md](DESIGN.md) | Why it is a relay computer; card cage; build philosophy |
| [docs/RELAY-CPU.md](docs/RELAY-CPU.md) | Emulator = board contract (v0.1 microarchitecture) |
| [docs/OS-BRINGUP.md](docs/OS-BRINGUP.md) | Ports, UART, CF boot, Contiki/FUZIX notes |
| [docs/TIMING.md](docs/TIMING.md) | Measured Clack boot / `ls` / echo on the coil clock |
| [RELAY65_HARDWARE_IMPLEMENTATION.md](RELAY65_HARDWARE_IMPLEMENTATION.md) | Datapath reverse-engineering + Design A/B/C relay budgets |
| [emulator/README.md](emulator/README.md) | Emulator flags, lamps, tests |
