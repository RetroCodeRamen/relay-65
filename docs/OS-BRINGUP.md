# OS bring-up on Relay-65

The emulator is the machine Contiki and FUZIX run on. Do not change this map
in an OS port without changing the emulator first.

To **run** Clack you do not need these trees: download
[v1.0.0](https://github.com/RetroCodeRamen/relay-65/releases/tag/v1.0.0) or
`./relay65 --gui --overclock --run --load software/images/console.bin`.

To **rebuild** firmware: `Source code/contiki-master` (also the `contiki`
symlink), `Source code/FUZIX-master`, and `third_party/cc65`.

## Frozen software-visible machine

| Item | Value |
| --- | --- |
| CPU | Documented NMOS 6502, microcoded, one 8-bit ALU; PC+1 and SP±1 are helpers, not that ALU |
| RAM | `$0000–$BFFF` paged (`$C018–$C01B`), `$D000–$FDFF`; Contiki window `$C010` |
| ROM | `$E000–$FFFF` **read** while `$C016` bit0=1. Writes always hit SRAM. FUZIX turns overlay off. |
| Boot | `$C017` bit0 autoboot: monitor IDE-loads LBA 1 → SRAM, `STA $C016`, `JMP $4002` |
| Console | UART `$C000` data, `$C001` status (bit0 RX, bit1 TX) |
| Timer/IRQ | `$C020` tick lo, `$C021` hi, `$C022` ctrl bit0=IRQ enable, `$C023` IFR |
| Disk | CF/IDE `$C100–$C107` (slot 0) |
| Net | ESP32 mailbox `$C200`. TCP on the ESP32. 6502: listen / read / write / close. |
| IRQ hook | ROM `JMP ($00F0)`, NMI `JMP ($00F2)` |
| Compiler | cc65 `--cpu 6502` (not 65C02). Config: `software/cc65/relay65.cfg` |

C programs load at `$0200`. Stack grows down from `$8000`. I/O at `$C000`
must not be used as RAM.

## cc65 runtime

```bash
make -C software/cc65
./relay65 --overclock --load software/cc65/hello.bin --max 20000
```

You should see `Relay-65 cc65 runtime`.

## Contiki (hello-world, then Clack)

Platform: `contiki/platform/relay65/`
(clock at `$C020`, printf via `software/cc65/write.s`).
IRQ ACK is `$C023` bit 7 from `software/cc65/crt0.s` (do not call C from IRQ).

Contiki version string in this tree is **3.x** (`contiki/core/contiki-version.h`).
The shell is **ClackShell 1.0**. `abt` prints those labels.

```bash
make -C software/contiki hello
./relay65 --overclock --load software/contiki/hello-world.bin --max 20000
```

UART should contain `Hello, world` and `Contiki on Relay-65`.

Live session. Type in the GUI serial pane; Enter sends CR. The console is a
C loop (`uart_read_line` → command or BASIC). It does **not** sit in Contiki
`process_run` / `serial_line_process`. Tick IRQ is off (`TICK_CTRL = 0`).
`abt` polls UART with `uart_getc` (space / CR, no echo).

```bash
make -C software/contiki
# also copies to software/images/console.bin (the v1.0.0 download image)
./relay65 --gui --overclock --run --load software/images/console.bin
```

`--gui` is a native window when tkinter is installed, otherwise the browser
at http://127.0.0.1:8065 (green SERIAL box). UART is also copied to the
terminal that launched `./relay65`. Wait for `Clack` in the motd. Do not
press RESET unless you want to restart from $0200.

UART starts with the Clack motd, then a `_>` prompt (path prefix when you
are not in `/`). Type `help` for commands, `man TOPIC` for manuals,
`ls /bin` for programs. `man abt` is the about-screen keys.

On the **20 ms/row** coil clock that is **1 min 55 s** to the prompt and
**38 s** for the first `ls` (datasheet 10 ms/row: 57.7 s and 19.1 s). Details:
[TIMING.md](TIMING.md). `--overclock` is how you use it on a PC.

Clack (the shell):

- `ls` / `cd` / `pwd` / `cat` / `echo` — RAM dirs `/` `/bin` `/etc` `/www` `/tmp`
- `edit` / `ed` — line editor (`/tmp/notes`, `/www/index.html`; `.` saves)
- `man` / `man basic` / `man abt` — short manuals
- `abt` — about Relay-65. First line, then wait. Space = next line.
  Enter = remaining lines with ~10 6502 `NOP`s between them. Enter after
  the last line returns to `_>`.
- `clear` `uname` `free` `hd` — scroll, name (`Relay-65 Contiki Clack`), RAM left, hex dump
- `time` — Contiki clock and `$C020` tick
- `io` — UART status, bank `$C010`, tick ctrl/IFR (does not read `$C000`)
- `bank` / `bank NN` — read or write the bank latch
- `peek 7000 4` — dump up to 16 bytes (avoid zeropage; cc65 lives there)
- `poke 7000 aa` — write bytes
- `watch on` / `watch off` — `[clock N]` heartbeat (off by default)
- `basic` — enter Relay65 BASIC V1.0 (integer, Tiny BASIC subset).
  `BYE` returns to Clack. In BASIC: `PRINT`, `LET`, `RUN`, `LIST`, `NEW`,
  `FRE`. `PEEK`/`POKE` use decimal or `$` hex (`POKE $7000, $AA`).

```bash
make -C contiki/examples/hello-world \
  TARGET=relay65 CONTIKI_WITH_IPV6=0 \
  CONTIKI=$PWD/contiki RELSTR=relay65
```

Use the `contiki` symlink (no spaces). IPv6/uIP is off for this first binary.

## FUZIX port

Platform: `fuzix/Kernel/platform/platform-relay65/` (from rcbus-6502).

RESET fetches the monitor. `--fuzix` writes `fuzix.bin` onto a CompactFlash
image at LBA 1 and closes the `$C017` autoboot jumper — same as imaging a card
and flipping the DIP. The 6502 copies 64 KiB through `$C100` itself.

```bash
make -C software/fuzix
./relay65 --gui --overclock --run --fuzix fuzix/Kernel/fuzix.bin
```

It signs on (NMOS 6502 — no 65C02 CPU probe). You should see the monitor banner,
then `FUZIX version`, RAM size, `ESP32: link up`, then `bootdev:`. There is no
root filesystem yet, so it waits there. Type `hda1` when a partition exists, or
build a card image with a filesystem and pass `--disk`.

```bash
./relay65 --gui --overclock --run --fuzix fuzix/Kernel/fuzix.bin --disk Images/relay65/disk.img
```

`--load` is still front-panel deposit (Contiki). `--overclock` only skips coil
waits. Neither is how FUZIX enters RAM.

## What the emulator is allowed to grow

- Extra slot cards later (would steal `$C300+` SRAM decode; not in v0.1)
- CompactFlash at `$C100` (emulator present; real card later)
- ESP32 NIC at `$C200` (mailbox; TCP stays on the ESP32)
- Physical SRAM 512 KiB, four page registers
- 65C02 opcodes as extra microcode rows
- Variable-duration microcycles (FAST/LOGIC/ADD/MEMORY) after bench timing

Not allowed: a second Python 6502 interpreter that OS code secretly runs on.
Not allowed: host pokes that skip the monitor (PC=`$4002`, `$C016` clear, kernel
`load_ram`). Imaging the CF card and the autoboot jumper are the real path.

PC+1, ADDR_SP, and the 8-bit ±1 helper are already in the emulator control
store. They are not a future OS-visible change.
