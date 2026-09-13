# Relay-65

A **luggable electromechanical 6502**: software-visible NMOS 6502 because a **relay datapath** executes it. Semiconductors are allowed for SRAM/ROM, microcode EEPROM, coil drivers, clocks, UART, CompactFlash, and an ESP32 network card. A hidden MCU that interprets opcodes is not the machine.

The Python emulator under `emulator/` is the **behavioral reference**. Contiki 3.x (with integer BASIC and the **Clack** shell 1.0), the monitor ROM, and a FUZIX kernel port already run on it. Physical hardware is designed, not built. First public software release: **[v1.0.0](https://github.com/RetroCodeRamen/relay-65/releases/tag/v1.0.0)**.

## Status

| Layer | State |
| --- | --- |
| ISA / binaries | Official NMOS 6502; illegal opcodes jam. cc65 `--cpu 6502` only (no 65C02). |
| Emulator | Microcoded 8-bit bus, one ALU, packed EEPROM control words. Design B fetch is ADDR_PC + hardware PC+1 in **one** µstep per opcode/operand byte. Stack uses ADDR_SP; INX/Y/SP use an 8-bit +1/−1 helper. Indexed EA still uses the ALU. |
| Software | **v1.0.0.** Monitor at `$E000`. Contiki 3.x + ClackShell 1.0 + BASIC. FUZIX kernel bring-up (CF boot, not a finished Unix box). TCP stays on the ESP32 mailbox, not uIP on the 6502. |
| Hardware v1 | **Design B** is in the emulator: ADDR_PC, hardware PC+1, ADDR_SP, 8-bit ±1, packed fetch. Physical boards are not built. Envelope **~450 DPDT** (populated a bit above the old 315–360 once stack/INX helpers are counted). |

## Design rules

1. The emulator is the hardware contract. If the emulator does it, the relay CPU does it.
2. Relays hold and route CPU data and perform ALU work. Silicon sequences coils and stores memory.
3. Spend relays on fetch, stack, and INX/Y — they run on every hot path. Do not duplicate the ALU to go faster.
4. Prefer real speed, an electromechanical datapath, and a buildable relay count over a 220-relay silicon-bus minimum.

Philosophy and card-cage intent: [DESIGN.md](DESIGN.md). Frozen emulator/hardware contract: [docs/RELAY-CPU.md](docs/RELAY-CPU.md). OS map: [docs/OS-BRINGUP.md](docs/OS-BRINGUP.md). Coil times: [docs/TIMING.md](docs/TIMING.md).

## Quick start

### Download (Windows / Linux)

**[v1.0.0 release](https://github.com/RetroCodeRamen/relay-65/releases/tag/v1.0.0)** — no Python, no compiler.

| File | What |
| --- | --- |
| `Relay-65-windows.exe` | Windows desktop app |
| `Relay-65-linux` | Linux desktop app (`chmod +x` if needed) |

Double-click. Clack is already loaded, the clock is warp, RUN is on. Type in the **serial** pane (green text). Wait for:

```
Clack on Relay-65
_>
```

Then `help`, `ls`, `abt`, `basic`. `man abt` is the about-screen keys. SPEED on the panel cycles RELAY (real coil waits) → 1s=1min → WARP.

If tkinter is missing, the same front panel opens in a browser at `http://127.0.0.1:8065`. Rebuild the apps with `pyinstaller pack/relay65.spec` ([pack/README.md](pack/README.md)).

### From a git checkout

Python **3.9+**. No pip packages for the emulator. `--gui` is a native window (tkinter) with the same layout as the browser panel.

```bash
# tests
cd emulator && python3 -m unittest discover -s tests -v

# from repo root — monitor ROM, UART on stdin/stdout
./relay65 --overclock --max 20000

# Clack (same image the download uses). START is STOP unless --run
./relay65 --gui --overclock --run --load software/images/console.bin
```

Windows (Python from python.org, which includes tkinter):

```text
py -3 relay65 --gui --overclock --run --load software/images/console.bin
```

`--panel` is a POSIX text front panel (not Windows). `--overclock` skips millisecond coil waits so Clack is usable on a PC. Default timing is ~20 ms per microstep. `--minute` (or SPEED) is 60×: one PC second = one minute of relay time.

Panel keys: `R` run, `S` stop, space = STEP ROW, `K` = STEP OP, `I` reset, `A`+hex examine, `D`+hex data, `E` examine, `P` deposit. Serial is the Teletype (`$C000`). Lamps are MACHINE (relay bus) and 6502 (A X Y SP P PC). HOST / REAL / WARP are wall time vs coil time.

## Repository layout

| Path | What |
| --- | --- |
| `./relay65` | Run the emulator from the repo root |
| `pack/` | PyInstaller spec; see [pack/README.md](pack/README.md) |
| `software/images/` | Shipped Clack image (`console.bin`) for v1.0.0 downloads |
| `emulator/` | CPU, ALU, memory, UART, CF, ESP32 mailbox, panel/GUI |
| `emulator/rom/monitor.s` | Front-panel monitor (assembled at run time) |
| `software/cc65/` | Bare-metal crt0, UART write, `relay65.cfg` |
| `software/contiki/` | Console + BASIC; builds against the `contiki` tree |
| `software/fuzix/` | CF pack helper; kernel is `fuzix/Kernel/platform/platform-relay65/` |
| `docs/` | CPU contract, OS bring-up, coil times |
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

**Contiki 3.x** — no IPv6/uIP on the 6502. Daily OS. The shell is **ClackShell 1.0** (`help`, `ls`, `man`, `edit`, `basic`, `abt`, `uname`). Type in the GUI serial pane. On the 20 ms coil clock, boot to `_>` is **1 min 55 s**; first `ls` is **38 s**. See [docs/TIMING.md](docs/TIMING.md).

**`abt`** — about text, one line at a time. Space = next line. Enter = the rest (~10 6502 `NOP`s between lines). Enter again when it is done to return to `_>`.

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
| [docs/OS-BRINGUP.md](docs/OS-BRINGUP.md) | Ports, UART, CF boot, Clack commands, Contiki/FUZIX notes |
| [docs/TIMING.md](docs/TIMING.md) | Measured Clack boot / `ls` / echo on the coil clock |
| [pack/README.md](pack/README.md) | Frozen Windows/Linux apps (v1.0.0) |
| [RELAY65_HARDWARE_IMPLEMENTATION.md](RELAY65_HARDWARE_IMPLEMENTATION.md) | Datapath reverse-engineering + Design A/B/C relay budgets |
| [emulator/README.md](emulator/README.md) | Emulator flags, lamps, tests |
