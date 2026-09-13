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
| ALU | **One** 8-bit ALU, reused for EA, ADC, memory INC | Relays are expensive; cycles are cheap. No second ALU. |
| PC increment | Dedicated PC+1 + ADDR_PC (Design B) | Packed with opcode/operand fetch: one EEPROM row, dual Φ2 LOAD. |
| SP increment | 8-bit REG_INC/DEC helper (shared with INX/Y/MARL) | Not the general ALU. ADDR_SP puts `$0100\|SP` on A[15:0]. |
| Shifts | Inside the ALU | ASL/LSR/ROL/ROR are ALU ops, not a second shifter card. |
| Temporaries | Relay-visible: IR, MDR, MAR, T, ALU_A, ALU_B | Needed for sequencing; still observable. |
| Microcode | Horizontal control word in EEPROM | EEPROM outputs drive coil drivers almost directly. |
| Clock | Two phases per microstep + a settle wait | Matches contact operate/bounce. |
| Memory | Semiconductor SRAM + ROM; CPU only sees MAR + R/W + data | CPU never “indexes an array”; it performs bus cycles. |

The dedicated PC+1 and ADDR_PC bits are already the fetch path. Changing packing
(one vs two rows, END on the last useful word) is a microcode substitution.
Software must not notice.

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
  +------------------+     A[15:0] = PC / $0100|SP / MAR
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
| A[15:0] | Address card | PC if ADDR_PC, else `$0100|SP` if ADDR_SP, else MAR |
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
Memory INC/DEC still use that adder. INX/INY/DEX/DEY/SP±1/MARL±1 use a
shared **8-bit +1/−1 helper** (~10–12 DPDT, XOR + propagate from the selected
register Q). That is not a second ALU: no AND/OR, no carry-in from P.C, no
BCD.

**PC increment** (opcode and operand fetch) is hardware PC+1 plus ADDR_PC,
packed into **one EEPROM row** — Design B dual Φ2 LOAD. The general ALU is
**not** used for PC+1. The incrementer evaluates from PC Q during Φ1 (it does
not use the internal bus). Φ2 strobes dest LOAD (IR/MDR/MAR) and PC LOAD
together. Splitting those LOADs is only a current-spike fallback, not a missing
coil.

```
ADDR_PC; MEM → IR or MDR; PC ← PC+1     ; one row, two Φ2 LOADs
```

**Stack:** ADDR_SP puts `$0100|SP` on A[15:0] (~8 DPDT extra on the address
mux). PHA is one row: SRC on the bus, MEM_WR, SP−1 on the helper at Φ2.
ADDR_SP samples SP Q before that LOAD.

**Taken branch:** ALU A-input can be the live bus (~4 DPDT) and B-input can be
M7EXT (~1–4 DPDT). Operand fetch also LOADs ALU_B from the data bus. Relative
add is then two ALU rows, not six bus copies.

Indexed addresses (`abs,X`, `(zp),Y`, …) still use the **one** 8-bit adder
(T + X/Y, then ADC on the high byte).

That reuse is the point of the machine: you solder **one** 8-bit adder. PC+1,
SP±1, and INX/Y are incrementers because they showed up in every hot path.

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

v0.1 default oscillator is **leeway**: **10 ms per coil change** (operate +
release each padded to 10 ms). Two phases → **20 ms per microstep**.
`--timing datasheet` is 6 ms operate + 4 ms release → **10 ms per row**.
`--overclock` or GUI SPEED **WARP** skips the wait (host as fast as it can).
GUI SPEED **1s=1min** is 60× the 20 ms clock.

Front panel: HALT freezes the step counter; STEP ROW is one microstep; STEP OP
is one 6502 instruction; RUN lets the oscillator clock Φ1/Φ2. HOST / REAL /
WARP on the panel are wall time vs those same rows at the coil clock.

Measured Clack boot and `ls` on this clock: [docs/TIMING.md](TIMING.md).

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
| 6 | ADDR_PC[0], PC_INC[1], ADDR_SP[2], REG_INC[3], REG_DEC[4], ALU_A_BUS[5], ALU_B_M7EXT[6], ALSO_ALU_B[7] |
| 7 | reserved 0 |

1. **FETCH** — shared. Not stored per opcode.
2. **EXECUTE** — indexed by IR and uStep.

FETCH:

```
ADDR_PC; MEM → IR; PC ← PC+1     ; opcode from PC, not MAR; dual Φ2 LOAD
```

Operand `fetch_byte` is the same packed row with MDR instead of IR. EEPROM byte 6
bit0 = ADDR_PC, bit1 = PC_INC. They are allowed together on one word. Remaining
byte-6 bits are the small helpers: ADDR_SP (A=`$0100|SP`), REG_INC/DEC (8-bit
+1/−1 into DST, or SP when DST is MEM), ALU_A_BUS, ALU_B_M7EXT, ALSO_ALU_B
(also LOAD ALU_B from the bus on the same Φ2).

Then `uStep := 0` and EEPROM address becomes IR.

An instruction’s last useful micro-op sets **END** (not a trailing empty row,
except NOP). Sequencer returns to FETCH.

N/Z for loads and register transfers sample the internal bus (N=D7, Z=NOR(D)).
C/V, and BIT’s N/V/Z, still come from the ALU card when that row’s ALU op is
not NOP.
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

The CPU does not know about banks. It puts A[15:0] on the system bus
(PC, `$0100|SP`, or MAR); the memory card maps it.

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
- Read `ram[PC]` inside the CPU. Memory cycles use A[15:0] after ADDR_PC /
  ADDR_SP (PC vs stack vs MAR) plus MEM_RD/MEM_WR.
- Extra architectural registers that firmware can see but hardware will not have.
- Host-side boot shortcuts: poking PC to `$4002`, clearing `$C016` from Python, or
  `load_ram` of the kernel. `--fuzix` inserts a CF image; RESET still hits ROM.
- Cycle-accurate NMOS 6502 *timing* (dead cycles). We are not claiming that.
  We **are** claiming the same **results** in A,X,Y,SP,P,PC, memory, and I/O.

When you add a real board, add it here first as a card class, then solder it.

## 11. Front panel lamps (v0.1)

The chassis has room for two lamp banks. Neither replaces the other.

**MACHINE** taps the backplane (relay datapath):

| Row | Signal |
| --- | --- |
| MAR | Address register A15–A0. Fetch drives PC on the system bus when ADDR_PC is on; these lamps still show MAR. |
| BUS | Last D7–D0 on the internal bus |
| IR | Instruction register (opcode) |
| SEQ | RUN, WAIT (STOP), IRQ, sequencer state / Φ / uStep |

**6502** taps architectural registers (what software sees):

| Row | Signal |
| --- | --- |
| PC | Program counter |
| A X Y SP | Accumulators / index / stack |
| P | N V U B D I Z C. B is not stored; U is forced 1. |

Front-panel clock: **STEP ROW** is one EEPROM word (Φ0/Φ1/Φ2). **STEP OP** is one 6502 instruction. EXAMINE / DEPOSIT use ADDR SW / DATA SW while STOP. Halt is a pin, not a memory-mapped register.

Two access paths, same as the finished machine:

- **`--gui`** — serial + both lamp banks + CLOCK/MEMORY paddles + HOST/REAL/WARP.
  Tkinter window, or the same layout in a browser at `http://127.0.0.1:8065`.
  v1.0.0 Windows/Linux apps are this path with Clack preloaded ([pack/README.md](../pack/README.md)).
- **`--leds`** — `*` / `.` lamp strip on stderr, UART on stdout.
- **`--panel`** — POSIX text panel; UART on TCP port 6502. Space = STEP ROW, `K` = STEP OP. Not Windows.
