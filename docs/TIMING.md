# Relay wall-clock times (Clack)

These numbers are **microsteps × coil time**, not host Python time. The emulator
walks every EEPROM row. `--overclock` only skips the wait; it does not skip
6502 work.

Default oscillator: **20 ms per microstep** (10 ms operate + 10 ms release
leeway). Datasheet parts in `emulator/relay65/timing.py` are 6 ms + 4 ms =
**10 ms per row**. GUI SPEED `1s=1min` is 60× faster than 20 ms/row.

Measured 12 Sep 2026 against `software/contiki/console.bin`, path
`ContikiTests._boot_console`: monitor ROM present, program deposited at
`$0200`, sequencer starts in FETCH. **Not** counted: RESET vector, monitor
banner, CompactFlash, or typing before `ls`.

Locked by `ContikiTests.test_clack_relay_boot_and_ls_times`. If that test
fails, update this file in the same change.

## Boot to Clack prompt

UART:

```
Clack on Relay-65
_>
```

| | Value |
| --- | --- |
| Microsteps | **5,771** |
| 6502 instructions | **1,031** |
| 20 ms/row (build default) | **1 min 55 s** |
| 10 ms/row (datasheet) | **57.7 s** |

Same instruction count as before the microcode packing pass. Fewer rows per
instruction, not fewer instructions.

## `ls` (first command after the prompt)

UART:

```
ls
/bin/
/etc/
/www/
/tmp/
_>
```

| | Microsteps | 20 ms/row | 10 ms/row |
| --- | --- | --- | --- |
| First `/` of the listing | **819** | **16.4 s** | 8.2 s |
| Listing complete + prompt | **1,906** | **38.1 s** | 19.1 s |

That `ls` is assembly (`software/contiki/ls.s`) over a RAM VFS. A command
that dirties the listing cache first can add a little more (rebuild is
between commands, not while waiting for keys).

## Typing (not in the locked test)

After the prompt, the UART wait loop is `LDA $C001` / `LSR` / `BCC` in
`software/cc65/write.s`. Injecting a key mid-poll vs on a later poll changes
the first character.

| | Microsteps | 20 ms/row | 10 ms/row |
| --- | --- | --- | --- |
| First key after boot | 146 | 2.9 s | 1.5 s |
| Next key (steady echo) | 57 | 1.1 s | 0.6 s |

## What still costs rows

Hot opcodes are already packed (1-row FETCH, END on the last useful word,
ADDR_SP, 8-bit ±1, taken-branch ALU muxes). Remaining time is still **one
row = one coil phase**:

- Absolute LDA/STA in the UART poll (MAR from the operand, then the data cycle)
- Taken `BCC` while RX is empty
- Indexed EA and memory RMW on the general ALU

No second ALU. No FAST 8 ms class until the bench experiments in
[RELAY65_HARDWARE_IMPLEMENTATION.md](../RELAY65_HARDWARE_IMPLEMENTATION.md)
say the contacts will take it.

## How to re-measure

```bash
PYTHONPATH=emulator python3 -m unittest \
  emulator.tests.test_machine.ContikiTests.test_clack_relay_boot_and_ls_times -v
```
