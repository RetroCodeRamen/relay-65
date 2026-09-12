# Relay-65 FUZIX platform

Port of `platform-rcbus-6502` onto the Relay-65 map.

## Hardware the kernel sees

- UART `$C000` data, `$C001` status (bit0 RX, bit1 TX)
- Bank pages `$C018–$C01B` — four 16 KiB pages covering `$0000–$FFFF`
- `$C010` still selects the `$8000` window (Contiki); emulator aliases it onto page 2
- `$C016` bit0 — ROM overlay at `$E000` (0 = RAM, needed to boot)
- Tick IRQ `$C020–$C023`
- CompactFlash 8-bit IDE in slot 0 `$C100–$C107`
- ESP32 NIC in slot 1 `$C200–$C20F` — listen/read/write/close; TCP stays on the card

Kernel RAM pages **0–3**. Seven user process maps, bases **4,8,…,28**.

I/O hole `$C000–$C2FF` is not kernel code (`$C300+` may be). `$E000–$FFFF` is RAM once ROM is off. The monitor copies a trampoline to `$0100` before clearing `$C016`, because you cannot drop the overlay while fetching from EEPROM.

## Build

From the repo root (symlink `fuzix` avoids the space in `Source code`):

```bash
make -C fuzix/Kernel TARGET=relay65
```

Needs cc65 (`cl65` / `ca65` / `ld65`) on PATH.

Load the kernel the way the hardware will: image a CompactFlash card (kernel at
LBA 1), RESET into the monitor, autoboot jumper on `$C017`.

```bash
./relay65 --gui --overclock --run --fuzix fuzix/Kernel/fuzix.bin --disk Images/relay65/disk.img
```

(`disk.img` is optional until `make diskimage` after a filesystem build.)
`--fuzix` does not poke RAM or the program counter.

This is bring-up, not a finished Unix box. Disk image + userland come next.
