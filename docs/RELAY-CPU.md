# Relay-65 CPU: Emulator = Hardware Blueprint (v0.1)

This document is the contract between the Python emulator and the relay machine.
If the emulator does something, the hardware is expected to do the same thing
with relays, EEPROM, and semiconductor support — not with a hidden microcontroller
executing 6502 opcodes.

**Design rule (from DESIGN.md):** Normal 6502 software runs because relay logic
performs the CPU work.

---

## 1. What we froze for v0.1

These were open in the philosophy draft. The emulator treats them as decided so
software and future boards share one map. Changing them later means changing
microcode and this document together.

| Topic | v0.1 decision | Why |
| --- | --- | --- |
| Internal datapath | **One** 8-bit bus | Fewer backplane pins and fewer bus-driver relays. Time-multiplex everything onto it. |
| ALU | **One** 8-bit ALU, reused for everything | Relays are expensive; cycles are cheap. |
| PC increment | **Dedicated 16-bit +1** (`CW.pc_inc`); fetch uses **PC on A[15:0]** (`CW.addr_pc`) | Software-invisible microcode substitution (Design B). ALU still does EA/SP/INX. |
| SP increment | Same ALU | Identical 8-bit inc/dec sequence as INX, just targeting SP. |
| Shifts | Inside the ALU | ASL/LSR/ROL/ROR are ALU ops, not a second shifter card. |
| Temporaries | Relay-visible: IR, MDR, MAR, T, ALU_A, ALU_B | Needed for sequencing; still observable. |
| Microcode | Horizontal control word in EEPROM | EEPROM outputs drive coil drivers almost directly. |
| Clock | Two phases per microstep + a settle wait | Matches contact operate/bounce. |
| Memory | Semiconductor SRAM + ROM; CPU only sees MAR + R/W + data | CPU never “indexes an array”; it performs bus cycles. |

A later dedicated PC+1 helper is allowed if bench timing shows fetch is too
slow — but it must remain a **microcode substitution** (one control bit that
today expands to an ALU sequence). Software must not notice.

---

## 2. Card cage (what to build)

The emulator’s Python modules are the cards. Build them in this order; each
module is independently testable, matching DESIGN.md §13.

```
                    PASSIVE BACKPLANE
  +------------------+     D[7:0] (internal CPU bus)
  | Control/Microcode |<--- Φ1/Φ2, RESET, HALT, STEP
  |  EEPROM + step    |---> SRC*, DST*, ALU*, MEM_RD/WR, CONST[7:0]
  +------------------+
  +------------------+
  | Register bank     |  A, X, Y, SP, P, T     (identical 8-bit slices)
  +------------------+
  +------------------+
  | ALU               |  ALU_A, ALU_B latches, F-block, C latch, flags
  +------------------+
  +------------------+
  | PC / Address      |  PCL, PCH, MARL, MARH, MDR, IR
  +------------------+     A[15:0] = MAR (not live PC)
  +------------------+
  | Memory / System   |  SRAM, ROM, address decode, bank latch
  +------------------+
  +------------------+
  | I/O console       |  UART at $C000 (expansion-style registers)
  +------------------+
```

**Backplane is passive.** It only carries buses, power, clocks, and decoded
selects. No “smart” CPLD on the backplane in v0.1.

### System bus (expansion / memory)

This is what peripherals see. It is **not** a 6502 chip pinout.

| Signal | Owner | Notes |
| --- | --- | --- |
| A[15:0] | Address card | MAR for EA/stack/vectors; **PC** when `ADDR_PC` (opcode/operand fetch) |
| D[7:0] | Memory or CPU MDR | Shared with internal bus during MEM_RD/MEM_WR, or buffered later |
| MEM_RD | Control | Active after settle; memory/UART drive data |
| MEM_WR | Control | Active after settle; memory/UART sample data |
| RESET | Control | |
| IRQ, NMI | Wired-OR to control | Sequencer polls these between instructions |
| SLOTSEL[n] | Memory decode | Expansion windows at $C100, $C200, … |
| +5 V, +12 V, GND | PSU | Coil vs logic split; many GND pins |

v0.1 emulator uses one data bus for both internal transfers and memory cycles.
If noise on the real backplane requires splitting CPU-internal vs system data,
do it with buffers on the memory card — **do not** change the micro-ops.

---

## 3. One bus, time-multiplexed

Every register slice is the same circuit:

1. **OE (output enable)** — eight relays (or one analog switch per bit) put the
   register onto D[7:0].
2. **LOAD** — on Φ2, after settle, clocks the bus into the register.

Only one OE may be true in a microstep. The control ROM encodes a 4-bit `SRC`
and a 5-bit `DST`. That is the entire datapath “instruction.”

Sources (`SRC`): none, A, X, Y, SP, P, PCL, PCH, MARL, MARH, MDR, T, MEM, ALU, CONST, M7EXT  
Destinations (`DST`): none, A, X, Y, SP, P, PCL, PCH, MDR, T, MARL, MARH, ALU_A, ALU_B, IR, MEM (write strobe)

`CONST` is eight EEPROM bits (semiconductor) driven onto the bus. That is how
we get 0, 1, $FF, $01 (stack page), flag masks, and vector addresses **without**
a ROM of relay constants.

`M7EXT` is MDR bit 7 copied to all eight bus bits ($00 or $FF). A handful of
relays. Used to sign-extend relative branches while still using the 8-bit ALU.

---

## 4. The ALU is the only arithmetic hardware

The ALU card has:

- **ALU_A**, **ALU_B**: 8-bit relay latches (same slice as A/X/Y).
- **Function block**: ADD/ADC, AND, OR, XOR, PASS_A, ASL, LSR, ROL, ROR.
- **C_latch**: carry out of the last ALU op, held across microsteps (one relay
  plus driver). This is *not* P.C unless microcode also does `FLAGS_LOAD`.
- **Flag outputs** N, Z, C, V combinational from the result (relays).
- **D_in** from P.D so ADC/SBC can do BCD.

SBC is ADC with ALU_B inverted (XOR $FF) and carry-in from P.C — same adder.
CMP is SBC that loads flags but does not write A.
INC is ADD with CONST 1. DEC is ADD with CONST $FF.

**PC increment** on opcode/operand fetch (and RTS) is a dedicated 16-bit
incrementer, one microstep, Φ2 LOAD after the memory sample:

```
ADDR_PC; MEM_RD → IR or MDR     ; PHASE 1 (A[15:0] = PC; inc evaluates)
PC ← PC + 1                     ; PHASE 2 (does not touch P)
```

Indexed addresses (`abs,X`, `(zp),Y`, …) still use the **general ALU**
(`add8`) with X/Y. SP±1 still uses the ALU. That reuse remains the machine:
you solder **one** 8-bit adder plus a thin PC+1 network.

---

## 5. Clock phases (what “step” means)

One **microstep** is one EEPROM row. The emulator’s `step()` still means that
row — it walks **Φ0 → Φ1 → Φ2** inside the call so lamps can show `Φn`, then
releases OE (idle Φ0). It is not one 6502 opcode.

```
Φ0  Release previous SRC (all OE off)
Φ1  Assert SRC OE; ALU function (combinational + C_latch)
Φ2  Pulse DST LOAD / MEM_RD sample into DST / MEM_WR; tick I/O Φ2
```

v0.1 default oscillator: **10 ms per coil change** (operate 6 ms / release 4 ms
plus bounce and lag). That is **20 ms per microstep**. `--timing datasheet`
uses 6+4 ms. `--overclock` or the GUI OVERCLOCK switch runs as fast as the host.

Front panel: HALT freezes the step counter; STEP runs one microstep; RUN
lets the oscillator clock Φ1/Φ2. The emulator `--trace` is that panel.

---

## 6. Microcode organization (EEPROM)

Packed by `emulator/relay65/eeprom.py`. Each row is **8 bytes**. Execute
address is `{IR[7:0], uStep[5:0]}` (64 rows per opcode). Unused rows are
`FF…FF` (jam), not NOP.

| Byte | Bits |
| --- | --- |
| 0 | SRC[3:0], DST[7:4] |
| 1 | ALU[3:0], CIN[5:4], MEM_RD[6], MEM_WR[7] |
| 2 | FLAGS[3:0], END[4], INVERT_B[5] |
| 3 | END_IF[3:0] |
| 4 | CONST |
| 5 | P_OR (B/U when pushing P) |
| 6 | ADDR_PC[0], PC_INC[1]; rest 0 |
| 7 | reserved 0 |

1. **FETCH** — shared. Not stored per opcode.
2. **EXECUTE** — indexed by IR and uStep.

FETCH (two settled phases, Design B):

```
ADDR_PC; MEM_RD → IR
PC ← PC + 1
```

Then `uStep := 0` and EEPROM address becomes IR.

An instruction’s last micro-op sets **END**. Sequencer returns to FETCH.
Illegal opcodes have no rows: unused EEPROM is `FF…FF` and the sequencer **jams**.

BRK/IRQ/NMI are extra execute programs: after END of an instruction, if NMI
pending or (IRQ and P.I=0), run the interrupt microprogram instead of FETCH.

---

## 7. Memory map (software-visible, hardware decode)

Logical 6502 space is 16-bit. Decode lives on the **Memory/System** card.

```
$0000–$BFFF   SRAM via four 16 KiB pages ($C018–$C01B; default 0,1,2,3)
$C000–$C00F   UART + Contiki bank $C010 + ROM ctrl $C016 + boot jumper $C017 + pages $C018–$C01B
$C020–$C023   tick/IRQ
$C100–$C107   CompactFlash (8-bit IDE) in slot 0; rest of $C1xx open-bus
$C200–$C20F   ESP32 network mailbox (slot 1); rest of $C2xx open-bus
$C300–$FFFF   SRAM via page 3 (kernel may live at $C300+). Slots 2–3 are
              reserved names only — v0.1 decode is RAM, not I/O.
$E000–$FFFF   ROM **reads** if $C016 bit0=1 (default); writes always SRAM
```

**Bank latch** `$C010` (write/read), Contiki window at `$8000`:

- Bank `0`: window is physical page 2 (`0x08000–0x0BFFF`).
- Bank `n` (1–4): pages 4–7 (extra SRAM). Writes also update page register `$C01A`.

**FUZIX pages** `$C018–$C01B`: 16 KiB each, 32 pages (512 KiB SRAM). Kernel uses 0–3.

**ROM overlay** `$C016` bit 0 (default 1): **reads** ROM at `$E000–$FFFF`. CPU **writes** still go to SRAM (write-through). FUZIX (or the monitor loader) stores 0 so `$FFFA` is RAM.

**Boot jumper** `$C017` bit 0: front-panel / DIP. 1 = monitor copies the kernel from CompactFlash (LBA 1, 128 sectors) after RESET and `JMP $4002`. The host `--fuzix` flag only inserts that card and closes the jumper.

**CompactFlash** `$C100–$C107`: 8-bit IDE task file. `--disk` is plugging a card in. Kernel image lives at LBA 1 on the card, not in a host poke of RAM.

The CPU does not know about banks. It puts MAR on A[15:0]; the memory card
maps it.

**UART** (I/O card, 6551-like subset, three registers):

| Addr | Name | Hardware |
| --- | --- | --- |
| $C000 | DATA | write: TX shift; read: RX holding |
| $C001 | STATUS | bit0 RX ready, bit1 TX ready |
| $C002 | CONTROL | stored; baud is host/FTDI until real UART clocking |
| $C010 | BANK | 16 KiB window at $8000 |
| $C020–$C023 | TICK | Φ2 → ÷256 → 16-bit count; IRQ on visible low-byte wrap if `$C022` bit0 |

ROM IRQ/NMI vectors `JMP ($00F0)` / `JMP ($00F2)` so firmware can install
handlers without reburning EEPROM.

There is **no** magic halt register in the memory map. Halt is a front-panel
pin on the control card. Test programs either loop or return to the monitor.

ROM is not writable from the CPU (programming is an external EEPROM programmer,
which in the emulator is `MemoryCard.load_rom`). SRAM under the overlay is.

---

## 8. Register and flag rules (NMOS-like, software-visible)

- RESET loads PCH:PCL from `$FFFC`, sets **I**, does **not** initialize A,X,Y,SP.
  The monitor must `LDX #$FF / TXS` itself.
- P bit 5 is 1 when pushed; B is 1 on PHP/BRK push and 0 on IRQ/NMI push.
  B is not a stored relay in P; it is OR’d onto the bus by control when pushing.
- JMP ($xxFF) uses **MARL increment without carry into MARH** so the NMOS
  page-wrap bug is the physical default. Contiki/FUZIX must not depend on 65C02
  JMP indirect. If we later add a 65C02 mode, it is a microcode change.

---

## 9. How to turn the emulator into boards

| Emulator module | Board | First hardware test |
| --- | --- | --- |
| `registers.py` | Register card, one 8-bit slice | Manual OE/LOAD, LEDs on D[7:0] |
| `alu.py` | ALU card | Load A/B, ADD, LEDs on result and C |
| `address.py` | PC/Address card | MAR→A[15:0], MDR, IR display |
| `memory.py` | Memory/System | Decode, SRAM R/W, ROM, bank |
| `uart.py` | I/O card | STATUS/DATA vs USB-serial |
| `signals.py` + `isa.py` + `eeprom.py` | Control/microcode | Burn the packed 8-byte rows |
| `cpu.py` | Clock/sequencer | Φ1/Φ2, STEP/HALT, FETCH/EXEC |
| `machine.py` | Passive backplane | Only connectors and power |

Build sequence (same as DESIGN.md §13): characterize relays → one register
slice → ALU → register+ALU on backplane → MAR/memory → control EEPROM →
this same monitor ROM.

---

## 10. What the emulator must not do

- Interpret 6502 opcodes in Python instead of walking control words.
- Read `ram[PC]` inside the CPU; only MAR+MEM_RD.
- Extra architectural registers that firmware can see but hardware will not have.
- Host-side boot shortcuts: poking PC to `$4002`, clearing `$C016` from Python, or
  `load_ram` of the kernel. `--fuzix` inserts a CF image; RESET still hits ROM.
- Cycle-accurate NMOS 6502 *timing* (dead cycles). We are not claiming that.
  We **are** claiming the same **results** in A,X,Y,SP,P,PC, memory, and I/O.

When you add a real board, add it here first as a card class, then solder it.

## 11. Front panel lamps (v0.1)

Physical lamps tap the backplane. The emulator prints them as `*` / `.`:

| Row | Signal |
| --- | --- |
| ADDR | MAR A15–A0 |
| DATA | last D7–D0 on the internal bus |
| IR | instruction register |
| STAT | RUN, WAIT (STOP), I, IRQ, N Z C V, sequencer phase |

Two access paths, same as the finished machine:

- **`--gui`** — lamps, paddle switches, and a serial terminal in one window.
- **`--leds`** — `*` / `.` lamp strip on stderr, UART on stdout.
- **`--panel`** — text panel; UART on TCP port 6502.
