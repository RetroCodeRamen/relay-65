# Relay-65 hardware implementation (architecture review)

**Status (12 Sep 2026):** this file is the **design history and relay budget**,
not the live control-store contract. The emulator has already been retargeted
to Design B fetch (ADDR_PC + PC+1 in one EEPROM row), packed EA/END/ALU
writeback, ADDR_SP, an 8-bit ±1 helper, and taken-branch ALU muxes. Live
contract: [`docs/RELAY-CPU.md`](docs/RELAY-CPU.md). Measured Clack times:
[`docs/TIMING.md`](docs/TIMING.md).

Early sections still describe the **then-current** 12-row FETCH / ALU PC+1
machine. That snapshot is kept so the Option A/B/C arithmetic stays
auditable. Do not copy those row counts into new boards.

**This document does not change firmware, binaries, or the software-visible
6502 contract.** Physical optimizations remain microarchitecture and
microcode timing, not a new ISA.

**Behavioral reference:** the Python emulator under `emulator/relay65/`. Contiki, BASIC, and the monitor already run on it. The physical machine must reproduce that software-visible behavior, not a MOS 6502 die, and not a new ISA.

**Relay accounting:** counts are **physical DPDT relays** (two mechanically linked SPDT poles per package), not contacts. The working cheap-relay class assumed below is a **5 V coil, ~40 mA, non-latching DPDT** with millisecond operate/release (G6K-class in `DESIGN.md` remains a size/footprint reference, not a frozen BOM).

**OLD DESIGN target:** roughly **220 DPDT** by using semiconductor buffers for most internal-bus source selection.

**NEW DESIGN target:** keep an **electromechanical datapath** (storage, routing contacts, ALU, architectural registers, PC, MAR/MDR/IR). Silicon remains allowed for microcode ROM, decode, coil drivers, RAM/ROM/peripherals, and clocks. Preferred total **approximately 450–500 DPDT**; comfortable **under 550**; hard ceiling **800**. Spend ~50–100 extra relays when they cut microcycles enough to raise real IPS.

**Do not optimize for minimum relay count alone.** Order of preference: real execution speed, understandable architecture, electromechanical datapath authenticity, reasonable relay count, buildability, debugging, power, software compatibility.

---

## How to read this document

The emulator is already a **horizontal microcoded 8-bit datapath**: one shared bus, one ALU, registers as OE/LOAD slices, memory via the address mux (PC / `$0100|SP` / MAR). Opcode “decoding” is EEPROM lookup of `{IR, uStep}`. That *is* the CPU. A gate-level 6502 clone would be a different machine.

Silicon is allowed for SRAM/ROM, microcode EEPROM, decode, coil drivers, clocks, UART, CF, ESP32, and similar support (`DESIGN.md` §3). Relays must perform architectural storage, the ALU, **and** the routing that moves bytes between those units.

Steps 1–3, 9, 11–12, and 16 reverse-engineer the **emulator as it was when
this review was written** (12-row FETCH, PC+1 through the ALU). That snapshot
is still the behavioral *style* (one bus, one ALU, EEPROM rows) but **not**
today’s row counts. Steps 4–8, 10, and 13–15 recorded the **OLD DESIGN**
(~220 relays, silicon bus OE, PC through the ALU). Those sections are kept.
The **NEW DESIGN** is specified in [Performance-Optimized Physical Architecture](#performance-optimized-physical-architecture).
The live control store is `emulator/relay65/isa.py` and [docs/RELAY-CPU.md](docs/RELAY-CPU.md).

---

# Step 1 — Reverse-engineer the existing emulator

## 1.1 What the CPU actually is

It is **not** an opcode interpreter and **not** a transistor 6502.

`CPU.step()` (`emulator/relay65/cpu.py`) loads one packed EEPROM row (`CW` in `signals.py`), walks Φ0/Φ1/Φ2, and drives `Src` / `Dst` / `AluOp` onto one 8-bit internal bus. Memory is `memory.read/write(self.addr.mar)` only.

Authoring of rows: `emulator/relay65/isa.py`.  
Packing: `emulator/relay65/eeprom.py` (`WORD=8`, `USTEPS=64`, `N_OPCODES=256`).  
Unpack/execute: `CPU._current` → `CW.unpack` → `_phi1` / `_phi2`.

**151** official NMOS opcodes have programs; **105** illegal opcodes are `JAM_WORD` (`FF…FF`) and halt the sequencer (`cpu.py` `cw is None` → `halted`). No undocumented 6502 opcodes, no 65C02 (`BRA`, `STZ`, `PHX`, `INC A`, …).

## 1.2 Programmer-visible 6502 state

| Name | Width | Where stored | Notes |
| --- | --- | --- | --- |
| A | 8 | `RegisterCard.a` | |
| X | 8 | `RegisterCard.x` | |
| Y | 8 | `RegisterCard.y` | |
| SP | 8 | `RegisterCard.sp` | Page `$01` supplied as `CONST 1` → `MARH` (`isa.mar_stack`) |
| P | 8 | `RegisterCard.p` | Bits: N V U B D I Z C (`signals.py` `FN`…`FC`). **B is not stored.** Unused bit U (`FU=0x20`) forced 1 on P load. RESET sets I (`FI`) and U; does not init A,X,Y,SP (`RegisterCard.reset_status`, `CPU.reset`) |
| PC | 16 | `AddressCard.pcl`, `.pch` | Exposed as `cpu.pc` for the panel only |

## 1.3 Internal (microarchitecture) registers

All 8-bit unless noted. Same OE/LOAD slice idea (`registers.py` docstring).

| Name | Where | Role |
| --- | --- | --- |
| T | `RegisterCard.t` | Scratch (abs lo, JMP/JSR, `(zp)` pointer lo) |
| MARL, MARH | `AddressCard` | System address `A[15:0] = MAR`, **never live PC** (`address.py`) |
| MDR | `AddressCard.mdr` | Memory data / operand holding |
| IR | `AddressCard.ir` | Opcode; execute EEPROM index |
| ALU_A, ALU_B | `ALUCard.a`, `.b` | ALU input latches |
| ALU result | `ALUCard.result` | Combinational/latched ALU output; source `Src.ALU` |
| C_latch | `ALUCard.c_latch` | Carry **between microsteps** (PC+1, EA+X). Not P.C unless `flags` loads C |
| flag_n/z/c/v | `ALUCard` | Combinational flags; copied into P only if `CW.flags` mask set (`apply_flags`) |

## 1.4 ALU (`alu.py` `ALUCard.evaluate`)

Primitives (`signals.AluOp`): `NOP`, `PASS_A`, `ADD`, `ADC`, `AND`, `OR`, `XOR`, `ASL`, `LSR`, `ROL`, `ROR`, `BIT`.

Carry-in (`Cin`): `ZERO`, `ONE`, `P` (P.C), `LATCH` (C_latch).

`invert_b`: XOR ALU_B with `$FF` before ADD/ADC. Used for **SBC** and **CMP** (`isa.binary(..., invert_b=True)`, `isa.cmp_reg` with `cin=Cin.ONE`).

**ADD vs ADC:** `ADD` forces cin=0 unless `Cin` is not `ZERO` (`alu.py` around the ADD/ADC branch). PC increment uses `ADD` then `ADC` with `Cin.LATCH`.

**Decimal:** if P.D set, `_adc` does nibble `>9` then `+6` adjust. Overflow V is still taken from the **binary** sum. Contiki/BASIC bring-up does not rely on `SED`; the behavior is still part of the contract.

**BIT:** Z from A∧B; N from B.7; V from B.6 (`AluOp.BIT`).

**Shifts:** operate on ALU_A; ROL/ROR use selected cin; C_latch ← C.

## 1.5 Buses

**One 8-bit internal bus.** Time-multiplexed. `CPU._drive` is the source mux; `_load` is the destination write. `last_bus` is the lamp tap, not extra ISA state.

System bus to memory/I/O: `MAR` + `MEM_RD`/`MEM_WR`. v0.1 shares the internal data bus with memory during those strobes (`docs/RELAY-CPU.md`). Split with buffers later if noise requires it; **do not change micro-ops**.

**CONST:** 8 EEPROM bits onto the bus (`Src.CONST`, `CW.const`). Not a relay constant ROM.

**M7EXT:** MDR bit 7 copied to all 8 bus bits (`Src.M7EXT`) for signed branch page adjust (`isa.branch`).

## 1.6 Instruction register and “decode”

There is **no PLA**. After FETCH, `state=EXEC` and the row is `execute[(IR<<6)|uStep]` (`eeprom.ControlStore.execute_word`).

FETCH (`isa.FETCH`, 12 rows):

1. PCL→MARL, PCH→MARH  
2. MEM_RD→MDR  
3. MDR→IR  
4. PC←PC+1 via ALU (`pc_inc`, 8 rows)

Then execute program until `CW.end` or `CW.end_if` true.

## 1.7 Program counter

Always ALU: `pc_inc()` in `isa.py` (8 rows). No dedicated +1 hardware in v0.1 (`DESIGN.md` / `RELAY-CPU.md`). A later PC+1 helper is allowed only as a **microcode substitution** software cannot see.

## 1.8 Stack pointer

8-bit. `sp_inc` / `sp_dec` are ALU ADD with CONST `1` or `$FF` (4 rows each). Stack address: `mar_stack` = SP→MARL, CONST `$01`→MARH.

## 1.9 Processor status

- Load P: `(value | FU) & ~FB` (`CPU._load` `Dst.P`).  
- Drive P: `(p | FU | cw.p_or)` (`_drive` `Src.P`).  
- PHP/BRK: `p_or=FU|FB`. IRQ/NMI push: `p_or=FU` only (`isa.php`, `isa.interrupt`).  
- Flag updates: `CW.flags` bitmask `FLG_N/Z/C/V` on Φ2 (`_phi2`).  
- CLC/SEC/CLI/SEI/CLD/SED/CLV: ALU AND/OR immediate into P (`p_and` / `p_or`).

## 1.10 Addressing (`isa.py` `EA`)

| Mode | Helper | Mechanism |
| --- | --- | --- |
| imm | `ea_imm` | `fetch_byte` → operand in MDR |
| zp | `ea_zp` | lo→MARL, CONST 0→MARH |
| zpx/zpy | `ea_zpx`/`ea_zpy` | 8-bit ADD, MARH=0 (6502 zp wrap) |
| abs | `ea_abs` | lo in T, hi in MDR, then MAR |
| abs,X/Y | `ea_absx`/`ea_absy` | `add8`: 16-bit add with C_latch into MAR. **Always** pays carry into MARH (no 6502 “skip dummy cycle”) |
| (zp,X) | `ea_indx` | X add then `zp_ptr_to_t_mdr` |
| (zp),Y | `ea_indy` | pointer then Y add to 16-bit MAR |

`zp_ptr_to_t_mdr`: hi byte from `MARL+1` with **8-bit** ADD (6502 zero-page wrap).

`fetch_byte` = 11 rows (2 MAR + 1 MEM + 8 PC+1).

## 1.11 Memory interface

CPU: MAR must be valid, then `mem_rd` or `mem_wr`.  
`MemoryCard` (`memory.py`): 512 KiB paged SRAM, ROM overlay `$E000` reads if `$C016` bit0, **write-through** to SRAM, UART/tick/pages/IDE/ESP32 decode. **Not relay CPU.** Open bus `$FF` on undecoded I/O holes.

## 1.12 Microinstruction format (`CW.pack`, 8 bytes)

| Byte | Field |
| --- | --- |
| 0 | SRC[3:0], DST[7:4] |
| 1 | ALU[3:0], CIN[5:4], MEM_RD[6], MEM_WR[7] |
| 2 | FLAGS[3:0], END[4], INVERT_B[5] |
| 3 | END_IF[3:0] (`Cond`) |
| 4 | CONST |
| 5 | P_OR |
| 6–7 | 0, reserved |

## 1.13 Microcode addressing and branching

| Page | Size | Address |
| --- | --- | --- |
| FETCH, RESET, IRQ, NMI | 64 rows × 8 bytes each | `uStep` |
| EXECUTE | 256 × 64 × 8 = 131072 bytes | `{IR[7:0], uStep[5:0]}` |

**Branching:** only `end_if` (test P, skip rest of instruction, go to `_end_instruction`) and `end` (next FETCH, or IRQ/NMI). No computed micro-goto, no loops in microcode.

`Cond`: NEVER, ALWAYS, Z, NZ, C, NC, N, NN, V, NV (`cpu._cond`).

Branches in ISA: `isa.branch` fetches offset, `CW(end_if=…)` **not-taken** exits, else ADD offset to PCL and ADC `M7EXT` into PCH.

## 1.14 Clock / state machine

`CPU.state`: `RESET` | `FETCH` | `EXEC` | `IRQ` | `NMI`.  
`ustep`, `phi` ∈ {0,1,2}, `oe_src`.

Each `step()` (`cpu.py`):

- Φ0: all OE off  
- If `end_if` true: tick timer, end instruction  
- Else Φ1: assert SRC OE; MEM_RD or drive bus; ALU `evaluate`  
- Φ2: optional `apply_flags`; LOAD dst / MEM_WR  
- OE off; `timer.on_phi2()`; `ustep++` or END  

`WallClock` (`timing.py`): default **10 ms per coil edge × 2 = 20 ms/microstep**; datasheet 6+4 ms; `--overclock` skips waits. Φ2 LOAD is specified as semiconductor (no extra relay time).

Front panel: `machine.running` is HALT/RUN (`machine.py`). Not a memory-mapped halt.

## 1.15 Interrupts and reset

**RESET microprogram** (`isa.RESET`, 9 rows): read `$FFFC`/`$FFFD` into PCL/PCH. I flag set in `reset_status`, not in those rows.

**After each instruction END** (`CPU._end_instruction`):

1. If finishing IRQ/NMI page → FETCH  
2. Else if `nmi_edge` → NMI page (`isa.nmi` → vector `$FFFA`, P push without B)  
3. Else if `timer.irq_line` and P.I=0 → IRQ page (`isa.irq` → `$FFFE`, P push without B)  
4. Else FETCH  

`interrupt()`: push PCH, PCL, P; SEI via `p_or(0x04)` without END; load vector. BRK uses same helper with dummy `fetch_byte` and `status_or=FU|FB`.

**NMI:** `nmi_edge` exists; nothing in v0.1 I/O sets it (front-panel hook later). IRQ line today is the tick IFR (`timer.py`).

Monitor ROM vectors: `JMP ($00F0)` / `JMP ($00F2)` so firmware installs handlers in RAM.

## 1.16 Memory R/W sequencing

Reads: Φ1 `memory.read(mar)` if `mem_rd` (or `Src.MEM`). Writes: Φ2 `_load` / `mem_wr`. One byte per row that sets those strobes.

## 1.17 Page crossing and branches

- **abs,X / (zp),Y:** always 16-bit add (`add8` / indy tail). Extra microcycles always, even without a carry. Software-visible address is still correct.  
- **JMP ($xxFF):** `jmp_ind` increments **MARL only** (ALU ADD then MARL; MARH unchanged) — NMOS wrap.  
- **Relative branch:** signed via `M7EXT`, not 65C02 extra cycle rules.

## 1.18 Stack ops

`push_mdr` / `pop_mdr`: MAR=$01SP, write/read MDR, SP±1 through ALU.

## 1.19 Compatibility / unimplemented

| Item | Behavior |
| --- | --- |
| Illegal opcodes | Jam (halt sequencer), not NOP |
| 65C02 | Not implemented |
| NMOS dead cycles | Not claimed; results in A,X,Y,SP,P,PC,memory,I/O are claimed |
| Decimal N/V | V from binary; decimal adjust on result/C |
| Front-panel `--load` | Deposit; not part of CPU datapath |

Implemented opcode list: `isa.build_execute_rom` (LDA/LDX/LDY, STA/STX/STY, ADC/SBC, AND/ORA/EOR, CMP/CPX/CPY, BIT, shifts RMW and acc, INC/DEC mem and X/Y, flag ops, transfers, PHP/PLP/PHA/PLA, JSR/RTS/RTI/BRK/JMP, branches, NOP `$EA`).

---

# Step 2 — Hardware-visible CPU state

## A. Must exist in the relay datapath

These *are* the CPU:

- A, X, Y, SP, P (stored bits N,V,D,I,Z,C; U strapped 1)  
- PCL, PCH  
- T, MARL, MARH, MDR, IR  
- ALU_A, ALU_B, adder/logic/shift result, C_latch  
- One 8-bit bus and the ability to connect **one** source and **one** destination per microstep  
- M7EXT (MDR.7 → byte of 0x00 or 0xFF)  
- invert_b on ALU_B  
- Flag combinational N,Z,C,V into P when microcode says so  

If these are silicon, the machine is not a relay CPU.

## B. Reasonable semiconductor support

Does not “compute the program,” sequences or stores memory:

- Microcode EEPROMs and `{IR,uStep}` addressing (`eeprom.py`)  
- uStep counter, Φ0/Φ1/Φ2 generator, RESET/FETCH/EXEC/IRQ/NMI sequencer (`CPU.state`)  
- 4-to-16 SRC/DST decode to coil drivers (EEPROM fields are 4 bits; 16 load lines)  
- MOSFET/transistor coil drivers and flyback  
- SRAM, ROM, bank/page latches, address decode (`memory.py`, `mmap.py`)  
- UART, tick divider, CF, ESP32  
- CONST byte (EEPROM outputs)  
- Crystal / oscillator; Φ2 pulse for LOAD (short, not coil-length)  
- `end_if` flag mux (test P bits → skip) can be a small PAL/MCU **or** a few relays; silicon is appropriate because it is sequencing, not ALU  

## C. Emulator-only artifacts

No hardware counterpart required:

- Python `int` objects, `list[CW]` before packing  
- `CPU.microcycles`, `instructions` counters  
- `last_bus` except as a lamp tap of the real bus  
- `force_ram`, `load_rom` programmer path  
- `--overclock`, `WallClock` sleep  
- `halted` as Python flag — physically: jam = sequencer stop / WAIT lamp (same as illegal-opcode halt)  
- Packed image construction in `ControlStore.from_isa()` at process start  

---

# Step 3 — Micro-operations (as the emulator does them)

Every execute row is already one of these. Do not invent new ones.

| MICRO-OP | INPUT | OUTPUT | SIDE EFFECTS | FLAGS | LIKELY HARDWARE |
| --- | --- | --- | --- | --- | --- |
| SRC → bus | Selected register / CONST / MEM / ALU / M7EXT | D[7:0] | OE coils | — | Source mux or per-byte OE |
| bus → DST | D[7:0] | Named latch | Φ2 LOAD | — | Destination decode + latch |
| MEM_RD | MAR | bus (then usually MDR) | SRAM/ROM/I/O read | — | Silicon memory |
| MEM_WR | bus, MAR | memory[MAR] | write strobe | — | Silicon memory |
| ALU op | ALU_A, ALU_B, cin, invert_b, P.D | result, C_latch, flag_* | Combinational on Φ1 | Loaded on Φ2 if `flags≠0` | Relay ALU |
| FLAGS_LOAD | flag_* mask | P | U forced 1 | N/Z/C/V subset | 4 AND into P bits |
| PC+1 | PCL,PCH | PCL,PCH | 8 rows; uses C_latch | none (must not hit P) | Same ALU |
| SP±1 | SP | SP | 4 rows | none | Same ALU |
| EA add8 | T, MDR, X/Y | MAR | C_latch | none | Same ALU |
| end / end_if | P or always | sequencer | FETCH or IRQ/NMI | — | Sequencer silicon |
| P_OR on drive | P, `p_or` | bus | PHP/BRK B bit | — | OR into P drivers |
| JAM | illegal IR | — | halt | — | Sequencer trap |

`xfer(src,dst)` in `isa.py` is SRC→bus→DST. `alu(op)` is ALU op with SRC/DST none.

---

# Step 4 — Map datapath to relays (8-bit parallel)

> **OLD DESIGN** for bus gating and “one DPDT = one stored bit” as an untested given. **NEW DESIGN** re-evaluates both in the performance architecture section. The 8-bit parallel rule is unchanged.

**Do not** serialize to a 1-bit ALU. The emulator is 8-bit parallel; serial would change timing vs microcode row counts unless microcode were rewritten (forbidden here). The physical CPU may **reduce row counts** later with equivalent faster hardware; it may not change what software sees.

Recommended physical picture (matches `registers.py` + `alu.py` + `address.py`):

```
 [A X Y SP P T] [PCL PCH MARL MARH MDR IR] [ALU_A ALU_B]
         \              |                         |
          \             v                         v
           ---- 8-bit internal bus <---- CONST, MEM, M7EXT, ALU.result
                          |
                    dest LOAD (Φ2)
```

**Register slice (1 bit):** one DPDT whose coil is the stored bit (energized=1), pole A = Q to a per-register byte buffer, pole B = complementary Q or hold indication. LOAD = drive coil from bus bit through a transistor gated by DST and Φ2 (set vs reset: bus=1 energize, bus=0 discharge). **1 DPDT per bit** is the working assumption. Continuous coil current for 1s is a PSU/thermal problem, not a relay-count problem; latching DPDT would cut power and is a BOM option.

**Per 8-bit slice:** 8 DPDT.

**Slices required:** A, X, Y, SP, P, T, PCL, PCH, MARL, MARH, MDR, IR, ALU_A, ALU_B = **14 × 8 = 112** storage relays.

P only needs 6 stored bits (N V D I Z C); U strapped, B not stored → **save 2** (use 6 relays + straps). Expected P = 6.

**IR** must be relay-visible (design rule: observable opcode). 8 DPDT.

MAR is the physical address register; 16 DPDT.

---

# Step 5 — ALU implementation

Emulator ALU must provide ADD/ADC (with invert_b and four cin sources), AND, OR, XOR, PASS_A, BIT, and four shifts. Subtraction, compare, INC/DEC, PC+1, SP±1, indexing, and branches already **reuse ADD** in microcode. Do not add a subtractor, incrementer, or second ALU.

### One-bit slice (concept)

Inputs: `Ai`, `Bi`, `Cin`, `invert_b`, plus function bits from EEPROM (decoded once per byte, fanned to slices).

1. **B′ = B ⊕ invert_b** — 1 DPDT (swap B vs ~B onto the adder input).  
2. **Full adder** SUM, Cout from A, B′, Cin — typically **4 DPDT** (XOR/XOR for sum; carry as majority with spare poles).  
3. **AND / OR** — **1 DPDT each** (or one DPDT with both poles for AND on one pole and OR on the other if the function mux selects).  
4. **XOR** — often already inside the adder; tap SUM with Cin=0 and B′=B.  
5. **Shift** — not in the 1-bit adder: **inter-slice wiring**. ASL = `{A[6:0],0}` with C←A7; LSR = `{0,A[7:1]}` with C←A0; ROL/ROR insert Cin. Byte-wide **result mux** (ADD vs LEFT vs RIGHT vs LOGIC): **2 DPDT per bit** (4:1).  

**Optimistic slice:** 1 + 4 + 1 + 2 = **8 DPDT/bit** → 8×8 = **64** plus a few byte-wide flag relays.  
**Expected:** **9/bit → 72** plus flags/BCD.  
**Pessimistic:** **12/bit → 96** if function mux is clumsy.

**Byte-wide extras:**

| Block | Expected DPDT | Notes |
| --- | --- | --- |
| Z (NOR of 8 result bits) | 4 | tree of poles |
| N | 0 | wire result[7] |
| V | 2 | `(~(A^B)&(A^SUM))[7]` |
| C_latch | 2 | 1-bit register + OE |
| Cin mux (0 / 1 / P.C / C_latch) | 2 | 4:1 with DPDT tree |
| BCD +6 nibble | 8 | only if D=1; can be second ADD of CONST 6/60 in **microcode** later; v0.1 emulator does it inside `_adc`. **Keep 8–12 relays** to match current evaluate() without microcode change |
| BIT N/V from B | 0 | wires B6/B7; Z from AND |

**ALU expected subtotal: ~90 DPDT** (72 slices + 18 flags/BCD/cin).

PASS_A = ALU op that copies A; no extra box.

---

# Step 6 — Register implementation

> **OLD DESIGN.** Assumed 1 DPDT/bit and **74HC541 source OE**. **NEW DESIGN** prefers relay source-enable contacts (4 DPDT per 8-bit sourced register). The 1-relay bit cell is **plausible but untested**; see Part 2 of the performance section.

**Finding:** one DPDT per stored bit is enough if:

- coil (or latching state) holds the bit  
- pole 1 is Q  
- pole 2 is ~Q or a lamp  

Bus **gating** should **not** consume a second relay per bit if a semiconductor 74HC541/245 per source is accepted as a **coil-side driver / bus buffer** (`DESIGN.md` drivers). That is the recommended split: **relays hold and show state; silicon switches the bus under SRC OE.**

If the review board forbids silicon on the internal bus, add **8 DPDT OE per sourced register** (11 sourced register bytes: A X Y SP P PCL PCH MDR T MARL MARH) = **+88**. That is the largest optional tax. ALU.result, CONST, MEM still need buffers (MEM/CONST are already silicon).

| Register | Bits | Optimistic | Expected | Pessimistic (extra OE relays) |
| --- | --- | --- | --- | --- |
| A,X,Y,SP,T | 8×5 | 40 | 40 | 80 |
| P | 6 | 6 | 6 | 12 |
| PCL,PCH | 16 | 16 | 16 | 32 |
| MAR | 16 | 16 | 16 | 32 |
| MDR, IR | 16 | 16 | 16 | 24 (IR need not drive bus often; MDR does) |
| ALU_A, ALU_B | 16 | 16 | 16 | 16 (loaded from bus; result is ALU) |
| **Register total** | | **110** | **110** | **~196** |

---

# Step 7 — Internal bus architecture

> **OLD DESIGN** recommended mux relay count ≈ 0 (HC buffers). **NEW DESIGN** still has **one** 8-bit bus and one-hot SRC, but SRC OE should be **relay contacts**, not the preferred datapath.

The emulator implies **exactly one 8-bit bus** plus ALU_A/ALU_B as **latched destinations**, not extra always-live A/B buses. Result returns via `Src.ALU` on the same bus.

**Relay cost of a pure-relay 16:1 mux:** 15 DPDT per bit × 8 = **120** (binary tree). Worse than per-register OE.

**Recommended:** one-hot SRC from 4-bit EEPROM field → 74HC154 → one OE pin per source. Relays of that source already present Q. **Mux relay count ≈ 0.** Complexity sits in wiring and one decoder.

**Destination:** 4-bit DST → 74HC154 → Φ2 AND → LOAD on that slice. **0 extra storage relays.**

**Do not** build separate A-bus and B-bus; the emulator never has both ALU inputs loaded in one row.

---

# Step 8 — Program counter and address handling

> **OLD DESIGN:** reuse ALU for PC+1; no PC→address bypass. Workload traces later showed PC+1 is about **half of all microsteps**. **NEW DESIGN** spends relays on a dedicated incrementer and PC/MAR address select. Software-visible PC is unchanged.

| Function | Emulator (current microarchitecture) | OLD physical recommendation |
| --- | --- | --- |
| PC+1 | 8 ALU rows every FETCH | **Reuse ALU.** Dedicated +1 is a future microcode swap if FETCH dominates too much |
| SP±1 | 4 ALU rows | Reuse ALU |
| Index / branch / JMP wrap | ALU | Reuse ALU |
| MAR | explicit loads | Relay MAR, 16 bits |

**Performance cost of no PC+1 (OLD):** FETCH is 12 rows of which 8 are increment. LDA immediate is 27 microsteps total. **NEW DESIGN** counts this as the dominant trace hotspot (~50% of microsteps) and pays for hardware PC+1.

---

# Step 9 — Microcode implementation

Documented exactly by `isa.py` + `eeprom.py` + `cpu.py`.

| Item | Value |
| --- | --- |
| Depth execute | 256 × 64 = 16384 words |
| Width | 64 bits (8 bytes); ~42 bits used |
| Address | `{page, IR, uStep[5:0]}` |
| Entry | FETCH then IR |
| Condition | `end_if` on P |
| IRQ/NMI/RESET | separate 64-word pages |
| Illegal | `FF` word → jam |

**Relay-controlled signals** (EEPROM bits after decode): 16 SRC enables, 16 DST loads, ~4 ALU op, 2 cin, invert_b, mem_rd, mem_wr, flags(4), end, end_if(4), const[8], p_or[8]. That is **~70 nets**, almost all **silicon decode + transistor drivers**, not 70 relays.

Encode SRC/DST as 4-bit fields (already done). Do **not** expand to 1 EEPROM bit per coil; that would widen the ROM without reducing relays.

Control-card relays: only if you insist on relay sequencers. **Expected control relays: 0–8** (optional jam/WAIT, NMI edge).

---

# Step 10 — Physical timing model

> **OLD DESIGN:** one conservative interval for every microstep. **NEW DESIGN:** variable-duration classes so ADD carry does not tax every register transfer.

Emulator `step()` is functionally Φ0→Φ1→Φ2 with **zero settle**. Hardware must wait.

Assume G6K-class: operate ~3–6 ms, release ~1–4 ms, bounce &lt;2 ms. `timing.py` already uses **6 ms operate / 4 ms release** datasheet and **10 ms leeway** per edge.

**Worst-case path on Φ1:** SRC coil operate + ALU ripple carry (8 slices). Adder ripple is contact delay in series: 8 × bounce/propagate. If each carry is another relay operate, **do not clock Φ2 until carry chain is dead**. Practical approach: **ALU evaluate uses the same 10 ms leeway as SRC OE** for v0.1 (carry relays chosen fast, or carry computed with fewer series stages). If carry is too slow, stretch Φ1 only on ALU rows (sequencer can use a longer EEPROM “ALU” timing bit later). v0.1: **one conservative interval for all rows.**

Proposed phases (matches emulator, names from the brief):

| Phase | Action | Time (conservative) |
| --- | --- | --- |
| Φ0 | Release previous SRC OE | 10 ms |
| Φ1 | New SRC OE; ALU inputs; settle including carry | 10 ms |
| Φ2 | Semiconductor LOAD / MEM strobe | &lt;1 µs–1 ms |
| Advance | uStep++ (silicon) | ns |

**Conservative clock:** 20 ms/microstep (**50 microsteps/s**), same as emulator default leeway.  
**Datasheet:** 10 ms/microstep (100 µsteps/s).  
**Likely after bench:** 8–12 ms/microstep if bounce is kind (**80–125 µsteps/s**).  
**Do not** assume 1 kHz; that would ignore operate time.

Cascaded stages: register OE → ALU invert → adder slice 0…7. That is the path to budget.

---

# Step 11 — Performance analysis

Lengths from `isa.py` (FETCH = 12 always, included in “total”).

| Instruction | Execute rows | Total µsteps | @20 ms | @10 ms | @8 ms |
| --- | --- | --- | --- | --- | --- |
| LDA #$nn | 15 | **27** | 0.54 s | 0.27 s | 0.22 s |
| LDA abs | 30 | **42** | 0.84 s | 0.42 s | 0.34 s |
| STA abs | 28 | **40** | 0.80 s | 0.40 s | 0.32 s |
| ADC # / abs | 16 / 31 | **28 / 43** | 0.56 / 0.86 s | 0.28 / 0.43 s | 0.22 / 0.34 s |
| INX | 5 | **17** | 0.34 s | 0.17 s | 0.14 s |
| Branch taken | 21 | **33** | 0.66 s | 0.33 s | 0.26 s |
| Branch not taken | 12 | **24** | 0.48 s | 0.24 s | 0.19 s |
| JSR | 42 | **54** | 1.08 s | 0.54 s | 0.43 s |
| RTS | 25 | **37** | 0.74 s | 0.37 s | 0.30 s |
| PHA | 9 | **21** | 0.42 s | 0.21 s | 0.17 s |
| PLA | 11 | **23** | 0.46 s | 0.23 s | 0.18 s |
| NOP | 1 | **13** | 0.26 s | 0.13 s | 0.10 s |

Mean over 151 implemented opcodes: **~35 µsteps** → **~1.4 IPS** at 20 ms, **~2.9 IPS** at 10 ms, **~3.6 IPS** at 8 ms.

**Usability:** Contiki/BASIC **will run the same binaries** and will feel like a click-click demonstration, not a 1 MHz Apple II. UART output is still fine (human typing is slower than 2 IPS). Tight polling loops and FUZIX userland will be painful until a later PC+1 microcode swap (~25% fewer µsteps on FETCH-heavy code). That is an expected property of this datapath, not a reason to serialize the ALU.

IRQ: 37-row page plus FETCH of the handler.

---

# Step 12 — Semiconductor boundary

| RELAY HARDWARE | SEMICONDUCTOR SUPPORT |
| --- | --- |
| A, X, Y, SP, P, T | Microcode EEPROM (8-bit × 64-row pages + 128 KiB execute) |
| PCL, PCH, MAR, MDR, IR | uStep counter, state (RESET/FETCH/EXEC/IRQ/NMI) |
| ALU_A, ALU_B, adder, logic, shifts, C_latch, flags | Φ0/Φ1/Φ2 oscillator, RESET RC |
| invert_b, M7EXT | SRC/DST 4-to-16, coil MOSFETs, flyback |
| Optional: a few jam/WAIT relays | CONST byte, bus buffers/transceivers |
| | SRAM 512 KiB, monitor EEPROM, page registers |
| | UART, tick ÷256 + 16-bit counter, CF, ESP32 |
| | Address decode `$C000`–`$C2FF` |

**Not acceptable:** ALU in an FPGA/MCU; A/X/Y as 74HC574 only; PC as a silicon counter while relays blink. **Acceptable:** HC574 **in parallel with** relay latches for debug, not instead of them.

---

# Step 13 — Relay count budget (physical DPDT)

> **OLD DESIGN** (~220 expected with silicon bus OE). **NEW DESIGN** budgets are in Part 15 of the performance section (~450–500 preferred with relay routing and PC acceleration).

| Subsystem | Optimistic | Expected | Pessimistic |
| --- | --- | --- | --- |
| ALU (8 slices + cin/flags/BCD) | 70 | 90 | 120 |
| A | 8 | 8 | 16 |
| X | 8 | 8 | 16 |
| Y | 8 | 8 | 16 |
| SP | 8 | 8 | 16 |
| PC (PCL+PCH) | 16 | 16 | 32 |
| P (6 bits) | 6 | 6 | 12 |
| IR | 8 | 8 | 8 |
| T | 8 | 8 | 16 |
| MAR | 16 | 16 | 32 |
| MDR | 8 | 8 | 16 |
| ALU_A, ALU_B | 16 | 16 | 16 |
| Bus/source switching | 0 (HC buffers) | 8 (M7EXT+spares) | 88 (relay OE) |
| Bus/destination switching | 0 | 0 | 8 |
| Control / IRQ / RESET | 0 | 4 | 16 |
| Miscellaneous (lamps isolation, spare) | 4 | 8 | 16 |
| **Total** | **184** | **~220** | **~444** |

**Expected ~220 DPDT** sits under 500 with margin. The pessimistic ~444 still under 800 and only happens if the internal bus is all-relay OE.

**If expected crept over 500** (it does not in this mapping), the first cuts would be: silicon bus buffers (already assumed), drop BCD hardware and document SED unused, share ALU_A with T (high behavioral risk — do not).

Largest consumers at expected: **ALU ~90**, **MAR+PC ~32**, **ALU input latches 16**, **A/X/Y/SP 32**, **IR+MDR+T 24**.

---

# Step 14 — Hardware simplifications (do not implement)

| CURRENT EMULATOR CONCEPT | PHYSICAL IMPLEMENTATION | RELAY SAVINGS | PERFORMANCE COST | COMPLEXITY COST | BEHAVIORAL RISK |
| --- | --- | --- | --- | --- | --- |
| 8-row `pc_inc` | Dedicated 16-bit +1 | 0 now; **saves time** not relays (adds ~12–20 relays) | FETCH −8 µsteps | New microcode bit | Low if software-invisible |
| P 8-bit store | 6 bits + straps | 2 | 0 | Wiring | Low |
| BCD inside `_adc` | Skip D-mode hardware until SED used | 8–12 | 0 for Contiki | Must not ship `SED` | Medium if forgotten |
| `end_if` in relays | PAL tests P | 0–6 vs relay decoder | 0 | PAL | Low |
| abs,X always 16-bit add | Same | 0 | Already slower than NMOS | — | None (already the contract) |
| Dual bus A/B | Do not build | Avoids +64 | — | — | Would be a new architecture |
| 1-bit serial ALU | Forbidden | Would “save” ALU relays | 8× ALU rows | Microcode rewrite | **Breaks reference** |

---

# Step 15 — Hardware construction order

> **OLD DESIGN** order assumed HC541 OE and ALU before PC+1. **NEW DESIGN** order is Part 19 (bit cell → 2-bit OE → bus contention → adder carry → PC incrementer → address select **before** ordering a full BOM).

Aligned with `DESIGN.md` §13 and actual modules (historical list):

1. Relay electrical fixture (operate/release/bounce/coil current) — `timing.py` numbers are placeholders until this exists  
2. 1-bit DPDT latch: LOAD from a switch, Q on a lamp  
3. 8-bit register slice + semiconductor OE buffer (matches `RegisterCard` bit)  
4. 1-bit ALU slice: ADD with cin/cout, invert_b  
5. 8-bit ALU + C_latch + N/Z/C/V lamps (`ALUCard`)  
6. Two slices on a backplane with 8-bit bus; manual SRC/DST  
7. Add PCL/PCH/MAR/MDR; prove MAR→SRAM cycle (`AddressCard` + `MemoryCard` silicon)  
8. IR + EEPROM execute of **one** opcode (e.g. `LDA #` + FETCH)  
9. Packed microcode dump (`./relay65 --dump-microcode`) on the Control card; Φ sequencer  
10. Remaining official opcodes (jam on unused)  
11. IRQ from tick card; RESET vector `$FFFC`  
12. Monitor ROM + UART  
13. Contiki/BASIC deposit path (`--load` equivalent: front-panel deposit)  
14. CF boot jumper `$C017` last  

---

# Step 16 — Hardware validation hooks

Single-step Φ or µstep on both machines; compare after Φ2.

Bring out (lamps + optional 74HC574 copies, not replacements):

| Signal | Why |
| --- | --- |
| A,X,Y,SP,P | `RegisterCard` |
| PCL,PCH,MAR,MDR,IR | `AddressCard`; lamps already conceptually in `leds.py` |
| ALU_A, ALU_B, result, C_latch | `ALUCard` |
| D[7:0] | `last_bus` |
| SRC, DST, ALU op, uStep[5:0], state | Control card |
| MEM_RD, MEM_WR, Φ0/Φ1/Φ2 | Timing compare |
| IRQ, I, jam/WAIT | `timer.irq_line`, `halted` |

Emulator already prints `CPU.snapshot()` and `--leds`. Physical panel should use the same bit order (MSB left) as `leds.bits`.

---

# Final deliverables (OLD DESIGN snapshot)

The following snapshot is the **~220-relay, silicon-bus-OE** conclusion. It is retained so the reverse-engineering trail stays intact. It is **not** the v1 physical recommendation.

## Existing CPU architecture

A **microcoded 8-bit relay-style 6502**: programmer-visible A,X,Y,SP,P,PC; internals T, MAR, MDR, IR, ALU_A/B, C_latch; **one bus**; **one ALU** used for arithmetic, PC, SP, EA, and branches; EEPROM rows `{SRC, DST, ALU, CIN, CONST, MEM, END, END_IF}`; FETCH then execute-by-IR; illegal opcodes jam; NMOS JMP-indirect wrap; interrupts as extra microprograms. Implemented in `cpu.py`, `isa.py`, `signals.py`, `alu.py`, `registers.py`, `address.py`, `eeprom.py`.

## Proposed physical CPU architecture (OLD)

Fourteen 8-bit DPDT register slices (P is 6 bits), one 8-bit parallel relay ALU (add with invert_b, logic, shifts), silicon microcode and Φ sequencer, silicon SRC/DST decode and bus buffers, semiconductor memory/I/O as in `mmap.py`. Same micro-ops as the emulator.

## Estimated relay count (OLD)

**Expected ~220 physical DPDT** (optimistic ~184, pessimistic ~444 with all-relay bus OE).

## Estimated clock rate (OLD)

**Conservative: 50 microsteps/s** (20 ms/row). **Datasheet: 100 µsteps/s.** **Likely after characterization: 80–125 µsteps/s.**

## Estimated instruction throughput (OLD)

**~1.4 IPS** conservative, **~3 IPS** at 10 ms/row. LDA # ≈ 27 rows; typical ≈ 35; JSR ≈ 54. This assumed PC+1 through the ALU and one timing class for every row.

## Biggest relay-count consumers (OLD)

1. ALU (~90)  
2. MAR + PC (~32)  
3. A/X/Y/SP (~32)  
4. ALU_A + ALU_B (~16)  
5. IR + MDR + T (~24)  

## Biggest technical risks (OLD)

1. Coil current if static 1 = energized  
2. ALU carry ripple vs a single Φ1 length  
3. Contact bounce on the shared bus  
4. BCD path  
5. Throughput too low — old mitigation was “maybe later PC+1”

## First physical prototype (OLD)

One DPDT bit, then an 8-bit slice with a 74HC541 OE.

**NEW DESIGN** first experiments and the v1 recommendation follow.

---

# Performance-Optimized Physical Architecture

This section revises the **physical** CPU. It does **not** change the software-visible ISA. The emulator remains the behavioral reference until a later, explicit microcode-engine change. Contiki, BASIC, the monitor ROM, and existing binaries stay valid.

**OLD DESIGN:** ~220 DPDT, semiconductor internal-bus source selection, PC+1 and SP±1 through the general ALU, one timing interval for every microstep.

**NEW DESIGN:** relay storage **and** relay data routing; silicon microcode/decode/drivers/memory/clocks; spend relays on fetch/PC paths that dominate real traces; variable microcycle timing; contact-mode carry rather than eight sequential coil operations.

**WHY:** traces of the unmodified emulator show opcode FETCH at ~36–40% of microsteps and **all `pc_inc` sequences at ~50–54% of microsteps**. A CPU that keeps PC+1 on the general ALU spends most of its life incrementing the program counter. A CPU that uses HC buffers as the internal source mux is not an electromechanical datapath.

Three contracts, kept distinct:

| Layer | What must stay | What may change |
| --- | --- | --- |
| **Software-visible** | NMOS 6502 register/memory/I/O effects; jam on illegal opcodes; NMOS `JMP ($xxFF)` wrap; B not stored; same memory map | Nothing user software can observe |
| **Current emulator microarchitecture** | `isa.py` row lists, 12-row FETCH, 11-row `fetch_byte`, 8-row `pc_inc`, ALU_A/ALU_B always loaded first | `WallClock` only, until we retarget microcode |
| **Proposed physical optimization** | Faster equivalent of the same architectural transfers | FETCH/`fetch_byte`/`pc_inc` row counts; optional bypass bits; timing-class bits |

If hardware is built as specified here, the emulator’s **microcode engine** (not the ISA) would later need a shorter FETCH page, `fetch_byte`/`pc_inc` substitution, and optional CW bits for address-source, PC_INC, timing class, and fused ALU destination. **Those emulator edits are identified, not implemented.**

---

## Part 1 — Challenge the existing assumptions

| Assumption | Classification | Why |
| --- | --- | --- |
| One DPDT per stored bit | **PLAUSIBLE BUT UNTESTED** | A non-latching coil can hold a 1 if a contact supplies self-hold and LOAD can break it. Not bench-proven on the cheap 5 V / ~40 mA class with flyback and LOAD=0 retention. |
| Register holding as “coil = bit” | **QUESTIONABLE** until experiment 1 | Release time, bounce, and LOAD/hold races are the failure mode. A 2-relay RS cell is the reliable fallback (~+110 DPDT). |
| LOAD as a MOSFET into the coil | **PLAUSIBLE BUT UNTESTED** | Allowed (coil driver). Must force ON for D=1 and force OFF (break hold) for D=0 for a full release interval. |
| Source OE via 74HC541 | **SHOULD BE CHANGED** for the preferred machine | Electrically fine (Design A). Data would leave relays through silicon muxes, which is not the preferred datapath. |
| Shared internal 8-bit bus | **PROVEN** in the emulator / **PLAUSIBLE** physically | Every `CW` has one SRC and one DST. Φ0 dead time is the contention rule. Needs the two-register experiment. |
| ALU ripple as “8 slices, same Φ1 as a transfer” | **SHOULD BE CHANGED** if carry coils are sequenced bit-by-bit | Eight *coil* delays would dominate the CPU. Carry through **already closed contacts** is a different, much faster path. |
| ALU function selection “typically four relays” | **QUESTIONABLE** | That was not a circuit. Count invert, XOR, sum, G/P, AND, OR, shift, result select. |
| PC increment through the general ALU | **SHOULD BE CHANGED** | Traces: ~2 `pc_inc` sequences per instruction, 8 rows each → **~50% of all microsteps**. |
| Memory fetch always via MAR copy of PC | **SHOULD BE CHANGED** for opcode/operand fetch | Two extra bus transfers per fetch. MAR remains required for EA. |
| Instruction fetch = 12 settled rows | **PROVEN** in current microcode; **SHOULD BE CHANGED** physically | Equivalent fetch can be 2 settled phases with PC address select + PC+1. |
| Operand `fetch_byte` = 11 rows | **PROVEN** in current microcode; **SHOULD BE CHANGED** physically | Same mechanism as opcode fetch without the IR load. |
| Semiconductor microcode / decode / drivers / RAM | **PROVEN** (project rule) | Does not compute the user program. |
| One timing interval for all ops | **SHOULD BE CHANGED** | ADD carry and PCL→MARL are not the same critical path. |
| Power “not a relay-count problem” | **QUESTIONABLE** | 40 mA × every stored 1 is a first-class PSU/thermal limit. ~50% ones on ~110 storage bits ≈ 2.2 A just to remember. |

---

## Part 2 — A real relay register bit

Target part class: **non-latching DPDT**, **5 V coil**, **~40 mA**, operate/release on the order of **1–8 ms**.

### Verdict

**One DPDT per stored bit is practical if and only if** a semiconductor LOAD gate is allowed to both **force-energize** and **force-release** the coil, and a **self-hold contact** retains a 1 after LOAD returns to 0. That matches the project rules (MOSFET coil drivers allowed).

It is not “a relay is a flip-flop by itself.” Without the LOAD/hold-break circuit, a non-latching relay forgets on release.

If experiment 1 fails (hold drop-out, LOAD race, diode-stretched release, welded hold contact), the **lowest-relay-count reliable alternative** is a **2-relay RS cell** (SET coil, RESET coil, cross-hold). That adds ~110 DPDT to every design below — which is why the bit-cell experiment is first.

Latching DPDT would cut static power nearly to zero. That is a **BOM change**, not assumed here.

### Conceptual 1-relay D latch (one bit)

- **Pole A — hold.** Common to the hold node. NO closes when picked up and feeds +5 V into hold so the coil stays on after LOAD ends.
- **Pole B — Q.** Common to Q. NO = Q true. NC = optional /Q.

**Coil suppression:** a diode across the coil is required for the MOSFET. A plain diode **lengthens release** (often 2–3×). Prefer **diode + zener** (or resistor-zener) so release stays a few milliseconds. **PLAUSIBLE BUT UNTESTED** on the cheap part.

**LOAD=1, D=1 (SET):** MOSFET path from +5 V **forces** operate. After operate time, pole A hold closes. LOAD may return to 0; the bit stays 1.

**LOAD=1, D=0 (RESET):** MOSFET **opens the hold path** and does not force the coil on. Armature releases; hold NO opens. LOAD must stay asserted for a **full release** (budget 5–10 ms until measured). Then LOAD=0 leaves the bit 0.

**LOAD=0:** neither force-set nor force-reset. State is hold (1) or de-energized (0).

**Q:** pole B NO, used by output-enable relays. Do not put coil current on this pole.

**LED:** resistor+LED across the coil (or hold node) indicates a stored 1 without stealing the Q pole.

**Output enable:** **not** on the storage relay. A separate OE relay (Part 3) connects Q to the internal bus.

**Power while storing 1:** **~40 mA continuous** at 5 V ≈ 0.2 W per bit. Eight 1s in A = 320 mA. That argues for a later latching BOM if heat/noise is ugly; it does not argue against 1-relay storage if the PSU is sized.

**Race to avoid:** never combinationally close a loop from incrementer outputs back into the same coils without Φ2 LOAD (Part 5 uses combinational contacts **into** the existing LOAD gate, same as a bus load).

---

## Part 3 — Relay-only register output gating

**OLD DESIGN:** storage relay Q → 74HC541 → internal bus.

**NEW DESIGN:** storage contact Q → **OE relay contacts** → internal bus. Semiconductor **decode** still turns exactly one SRC one-hot into one OE coil (74HC154 + MOSFET). Data does not pass through that silicon.

### Two bits per DPDT OE

An 8-bit source needs 8 SPDT “connect Q / isolate” switches. One DPDT is two SPDT. **4 DPDT per 8-bit sourced register** (12 relays per fully bus-readable byte: 8 storage + 4 OE).

Electrically sound **if**:

1. Φ0 releases **all** OE coils (break-before-make).
2. Φ1 energizes **one** SRC OE.
3. Isolated throw is open, not tied to another driver.
4. Bits sharing one DPDT enable together — which is exactly what byte OE needs.

A single OE-coil failure drops two bits; acceptable if experiment 2 passes. **v1 budgets paired OE.** Per-bit OE (8 DPDT/byte) is the serviceability fallback (~+50 relays).

IR, ALU_A, and ALU_B **never** appear in `Src` — **do not** buy OE for them. ALU **result** does (`Src.ALU`) — 4 DPDT. `Src.MEM` and `Src.CONST` stay silicon. `Src.M7EXT` is eight copies of MDR.7: **4 DPDT** with paralleled coils.

### Register relay count (NEW, 1 DPDT/bit storage + paired OE)

| Register | Sources bus? | Storage | OE | Total |
| --- | --- | --- | --- | --- |
| A | yes | 8 | 4 | 12 |
| X | yes | 8 | 4 | 12 |
| Y | yes | 8 | 4 | 12 |
| SP | yes | 8 | 4 | 12 |
| T | yes | 8 | 4 | 12 |
| P | yes (6 stored bits) | 6 | 3 | 9 |
| PCL | yes | 8 | 4 | 12 |
| PCH | yes | 8 | 4 | 12 |
| MARL | yes (`jmp_ind`) | 8 | 4 | 12 |
| MARH | yes | 8 | 4 | 12 |
| MDR | yes | 8 | 4 | 12 |
| IR | **no** | 8 | 0 | 8 |
| ALU_A | **no** | 8 | 0 | 8 |
| ALU_B | **no** | 8 | 0 | 8 |
| ALU result | yes | 0 (ALU) | 4 | 4 |
| M7EXT | yes | 0 | 4 | 4 |
| **Register/bus subtotal** | | **110** | **55** | **165** |

---

## Part 4 — Profile of the actual emulator

Instrumentation: `emulator/tools/profile_workloads.py` wraps `CPU.step` **without** changing control words. Peeking a CW is side-effect-free (calling `CPU._current()` before `step()` would illegally mutate FETCH→EXEC).

Workloads used the existing binaries. Counts are logical microsteps, not wall time.

| Workload | µsteps | Instructions | **µsteps/ins** |
| --- | --- | --- | --- |
| Monitor to `>` prompt | 45 639 | 1 383 | **33.00** |
| Contiki `hello-world` | 189 274 | 6 172 | **30.67** |
| Contiki console boot | 597 829 | 20 006 | **29.88** |
| Contiki console idle (100k steps) | 100 000 | 3 026 | **33.05** |
| BASIC enter + `PRINT 1+2` | 752 125 | 24 669 | **30.49** |
| BASIC `FOR I=1 TO 10` / `PRINT` / `RUN` | 400 000 | 12 513 | **31.97** |

Synthetic mean of 151 filled opcodes remains ~35 µsteps (Step 11). **Real Contiki/BASIC sit at ~30–33**, because they hammer branches, `(zp),Y`, INY/DEY, and zp stores rather than a uniform opcode average.

### Share of microsteps (equal-time rows)

| Activity | Monitor | Hello | Console boot | Idle | BASIC PRINT | BASIC FOR |
| --- | --- | --- | --- | --- | --- | --- |
| FETCH rows | 36.4% | 39.1% | 40.2% | 36.3% | 39.4% | 37.5% |
| EXEC rows | 63.6% | 60.8% | 59.8% | 63.7% | 60.6% | 62.5% |
| All `pc_inc` (8 × ALU_A←PCL) | **52.5%** | **51.1%** | **53.9%** | **54.4%** | **52.7%** | **51.9%** |
| mem_rd strobes | 7.6% | 8.0% | 7.9% | 7.7% | 8.1% | 7.9% |
| ALU ADD/ADC rows | 15.4% | 16.0% | 15.9% | 15.6% | 15.5% | 15.5% |
| ALU writebacks (`Src.ALU`) | 16.4% | 16.8% | 16.8% | 16.5% | 16.7% | 16.6% |

`pc_inc` sequences ≈ ALU_A sourced from PCL: **~2.0–2.25 PC+1 operations per instruction** (opcode increment + ~0.8–1.1 operand `fetch_byte` + occasional RTS).

ALU_A sources are dominated by **PCL and PCH**. After those, BASIC PRINT (24 669 ins): MDR 11 247, SP 4 358, A 3 444, T 2 794, MARL 2 651, Y 1 935, X 638, P 581. **A→ALU_A is ~14% of instructions and ~0.5% of microsteps.** MDR→ALU_A is ~46% of instructions but still ~1.5% of microsteps.

Opcode mix (illustrative):

- **Monitor prompt:** BEQ 16.5%, then a dump/print loop of JSR/RTS/LDA abs/LDA abs,X/PHA/PLA/AND #/STA abs/INX/JMP ~8% each.
- **Contiki hello:** STA `(zp),Y` 10.8%, BNE 9.9%, INY 9.0%, LDA `(zp),Y` 8.2%, LDY # 6.3%.
- **Console boot:** BNE 13%, STA `(zp),Y` 8.7%, ROL zp 7.8%, INY 7.5%, DEY 5.6%.
- **Idle:** BEQ/JSR/RTS/BNE/INC zp/LDA abs/JMP.
- **BASIC:** BNE, LDA `(zp),Y`, ROL zp, DEY, LDY #, STA zp, JSR/RTS — interpreter bytecode walk.

**Conclusion:** the only ~24-relay class change that can move IPS by **~2×** is **fetch/PC**. ALU input bypasses and INX helpers are percentage-point effects until PC is fixed. Do **not** duplicate the ALU.

---

## Part 5 — PC and fetch acceleration

### A. Direct PC → address bus

MAR must remain for zp/abs/indexed/stack. Opcode and operand fetches currently copy PCL→MARL, PCH→MARH (2 rows) so memory always sees MAR.

**NEW:** 16-bit 2:1 select, PC vs MAR. 16 SPDT = **8 DPDT**. One coil `ADDR_PC` from microcode. Contacts sit on A[15:0] to SRAM.

Electrically sound if PC and MAR Qs are steady and the DPDT commons are the memory address with throws to PC vs MAR (only one path selected).

### B. Dedicated PC+1

Do **not** send PCL through ALU_A, CONST 1 through ALU_B, ADD, write PCL, then ADC PCH.

**Derived count:** increment is XOR-with-carry-in and AND-propagate.

- Cin into bit 0 is wired 1.
- Propagate into bit *k* is the **series string of PC Q contacts 0..k−1** (already on storage relays) → **0 extra relays** for carry if a MOSFET senses the chain (or XOR is contact-mode).
- Sum bit *k* = PCk ⊕ cin_k: **1 DPDT per bit**, coil = cin_k (or a driver from the propagate chain), throws select PCk vs /PCk onto the incrementer output.

**Expected: 16 DPDT.** Optimistic 12 if LSB tricks are used (not worth it). Conservative **24** if PC+1 is latched in an extra 8 DPDT to isolate hold races.

**Race:** combinational +1 **outputs** feed the existing PC LOAD gates (same as bus LOAD). Do not close a loop while LOAD is false. Incrementer inputs are PC Q, which stay still until Φ2.

**Concurrent with memory read:** yes. PC is stable from the previous instruction. `ADDR_PC` places PC on A[15:0]; SRAM is silicon-fast; the incrementer evaluates from the same PC Q contacts. No wait for MAR.

### C. Combined fast fetch (respect settling)

Not one mechanical cycle. Two **settled phases**:

**PHASE 1 (MEMORY class):** `ADDR_PC`; memory OE; PC+1 network evaluates. Wait is the **8 DPDT address select**, not SRAM.

**PHASE 2 (FAST):** Φ2 loads IR (opcode) or MDR (operand) from the data bus **and** loads PC from incrementer outputs. Two semiconductor LOADs in one Φ2 are allowed (different destinations). If the current spike is ugly, split 2a IR / 2b PC — still far cheaper than 12 rows.

Then the sequencer goes EXEC.

**Operand `fetch_byte`:** same two phases, destination MDR not IR.

**Realistic microsteps:** **2** per opcode fetch, **2** per operand byte — not 1 and not 12.

RESET/IRQ/NMI vector fetches still use MAR (`$FFxx`). No PC path required.

---

## Part 6 — Quantify PC optimization benefit

Assumptions:

- Baseline FETCH 12, `fetch_byte` 11, `pc_inc` 8.
- Option A (incrementer only): FETCH = 2 MAR copy + 1 MEM + 1 IR + 1 PCLOAD = **5**; `fetch_byte` = **4**.
- Option B (address mux only): FETCH = 1 MEM + 1 IR + 8 `pc_inc` = **10**; `fetch_byte` = **9**.
- Option C (both): FETCH = **2**; `fetch_byte` = **2**.

Per-instruction extra `fetch_byte` ≈ (`PCL→MARL` − opcode fetches) / instructions.

| | Relays added | FETCH | fetch_byte | Monitor 33.00 | Hello 30.67 | Boot 29.88 | Idle 33.05 | BASIC 30.49 | FOR 31.97 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 0 | 12 | 11 | 33.00 | 30.67 | 29.88 | 33.05 | 30.49 | 31.97 |
| A incrementer | **16** (24 cons.) | 5 | 4 | ~19.2 | ~17.3 | ~16.8 | ~18.4 | ~17.2 | ~18.1 |
| B addr mux | **8** | 10 | 9 | ~27.8 | ~26.0 | ~25.5 | ~27.8 | ~25.8 | ~27.2 |
| **C both** | **24** (32 cons.) | **2** | **2** | **~13.3** | **~13.4** | **~12.9** | **~13.9** | **~12.8** | **~13.5** |

A/C remaining: subtract 7 per opcode fetch and 7 per extra `fetch_byte` for A; subtract 10 and 9 for C.

**Relative speed (microsteps, equal-time rows):**

| | vs baseline (hello / BASIC PRINT) |
| --- | --- |
| A | ~1.77× / ~1.77× |
| B | ~1.18× / ~1.18× |
| **C** | **~2.29× / ~2.38×** |

**Predicted IPS** (hello 30.67 → 13.4 µsteps) at a flat 20 ms/row: **3.7 IPS** (was 1.6). With FAST rows at 8 ms and remaining ADDs at 25 ms (Parts 11–12): **~7–9 IPS** (Part 16).

Option B alone is a poor buy. Option A is most of the win. Option C is the right pack: **8 extra relays over A** remove the MAR copy from the hottest path. **NEW DESIGN uses C.**

---

## Part 7 — ALU input fast paths

An 8-bit 2:1 is 8 SPDT = **4 DPDT**. Verified.

Until PC is fixed, A→ALU and MDR→ALU save **one row** buried under 50% PC+1.

| Bypass | Relays | µsteps saved when used | Workload (BASIC PRINT) | Speedup vs A | Speedup vs Design C fetch | Recommend? |
| --- | --- | --- | --- | --- | --- | --- |
| A → ALU A input | 4 | 1 | 14% of ins; **0.46%** of µsteps | ~0.5% | ~1.1% | **No** for v1 |
| MDR → ALU A input | 4 | 1 | 46% of ins; **1.5%** of µsteps | ~1.5% | ~3.5% | Optional in Design C |
| MDR → ALU B input | 4 | 1 | Binary ops; a few % of ins | ~1% | ~2% | Optional in Design C |
| X/Y → ALU | 4 each | 1 | INY/DEY/index | small | small | **No** |
| CONST → ALU B | 0 extra as a bus source | 1 | `pc_inc`/`sp_*`/INX until PC+1 exists | high until C | small after C | **No** separate box |

**Do not add every bypass.** Design B: none. Design C: **A and MDR into ALU A/B as two 4-DPDT muxes (8 relays)** only after fetch is done.

---

## Part 8 — ALU result fast writeback

Today: `alu(op)` then `xfer(Src.ALU, dst)` — two rows. Combining means Φ1 evaluates and Φ2 LOADs a decoded destination from ALU result contacts.

A **small** mechanism: keep `Src.ALU` OE, but allow DST ∈ {A,X,Y,SP,PCL,PCH,MARL,MARH} **in the same word as the ALU op**. The emulator already has both fields; `alu()` currently sets DST NONE. That is a **microcode packing change**, not a crossbar.

Physically the ALU result already has OE onto the bus. If Φ1 result is valid **and** we assert ALU OE and DST LOAD on Φ2, the existing bus **is** the writeback. **0 extra relays** if one row may set ALU op **and** DST.

**Caveat:** ALU evaluate must finish before LOAD — a timing-class issue (ADD rows already long), not a relay issue.

**OLD DESIGN** treated `alu()` and writeback as separate rows because that matched `isa.py` helpers.

**NEW DESIGN:** allow fused ALU+DST in microcode (**0–4 relays** if a buffer is wanted). **Reject** a destination crossbar. After PC accel, most writebacks were PCL/PCH and disappear. Remaining ~1–2 fused rows per typical LDA/ADC/INX → **~5–8%** on Design B. **Recommend: fuse in microcode later, 0 relays.**

---

## Part 9 — Increment/decrement helper

Shared 8-bit +1/−1 for INX/DEX/INY/DEY/SP/MARL.

Count: **8 DPDT** XOR + existing Q contacts for propagate, plus 1 DPDT for +1 vs −1. **~10–12 DPDT.**

After Option C, INX is **2 FETCH + 5 EXEC = 7** rows. A helper might make EXEC **2**. Save ~3 rows.

Frequency: console boot INY+DEY ≈ **13%** of instructions; hello ≈ **14%**; BASIC FOR much lower. Idle INC **zp** still uses memory RMW and the **general ALU**.

Speed benefit after C: 0.13 × 3 / 13 ≈ **3%**. Before C: lost in PC+1.

**Verdict: do not add for v1.** Revisit in Design C if INY/DEY still annoy. **Do not** build a second adder.

---

## Part 10 — Do not duplicate the ALU

Traces show **one** ADD/ADC hotspot: `pc_inc`. Once that has a dedicated incrementer, leftover ADD traffic is EA, ADC/SBC, SP, INX/Y, branches — exactly the general ALU.

**v1: one primary ALU. No second 8-bit adder.**

---

## Part 11 — Variable-duration microcycles

**OLD DESIGN:** ~20 ms/row for everything so ADD ripple could finish.

**NEW DESIGN:** 2-bit `TCLASS` in unused CW bytes 6–7. Sequencer silicon stretches Φ1.

| Class | Used for | Conservative wait | Likely after bench |
| --- | --- | --- | --- |
| FAST | SRC OE + LOAD, no ALU; PC LOAD from incrementer | **8–12 ms** | 5–8 ms |
| LOGIC | AND/OR/XOR/SHIFT; invert_b | **12–15 ms** | 8–12 ms |
| ADD | contact-carry ADD/ADC | **20–30 ms** contact-mode; **40–80 ms** if coils ripple per bit (**reject that ALU**) | 15–25 ms |
| MEMORY | address-select OE + silicon RAM | **8–12 ms** (wait on **relays**, not SRAM) | 5–10 ms |

The request’s example numbers (FAST 5–10, ADD 20–50+) are **order-of-magnitude right** only if carry is contact-mode. If carry is 8 sequential coil operates, ADD becomes **>50 ms** and the machine feels like it is only adding.

Microcode: FETCH phase 1 = MEMORY; phase 2 = FAST; `alu(ADD)` = ADD; `xfer` = FAST; `alu(AND)` = LOGIC.

Emulator later: `WallClock.wait(tclass)` instead of one leeway. **Not implemented now.**

---

## Part 12 — Ripple carry

If **each bit’s carry-out drives the next bit’s carry-in coil**, worst case is **8 mechanical operates in series**. At 5 ms each that is **40 ms** plus bounce. **SHOULD BE CHANGED.**

If each bit has **generate** and **propagate** relays whose coils depend only on A, B, invert_b (all bits **in parallel**, one operate time), then Cout is a **contact chain**. The ripple is **electrical** through metal, plus **one** bounce when those G/P contacts closed — not 8× operate.

Manchester-style: a sense line through propagate contacts; generate injects carry. Relays **must not** recoil on carry.

| Architecture | Relays (carry only, 8-bit, above invert/XOR) | Worst-case switching | Settle (order) | Complexity |
| --- | --- | --- | --- | --- |
| 1. Coil-per-bit ripple | 8 carry relays sequenced | **8 coil operates** | **40–80 ms** | Simple, **too slow** |
| 2. Contact ripple / Manchester (G/P parallel) | 8–16 (G and P; share with adder XOR) | 1 coil phase + electrical chain | **15–25 ms** total ADD class | Moderate; **v1 choice** |
| 3. 4+4 grouped carry | +8–12 group P/G | 1 coil phase + shorter chains | **12–20 ms** | If experiment 6–8 shows voltage drop/noise |
| 4. Full lookahead | +20–40 | 1 coil phase | ~10–15 ms | **Reject** for v1 |

**v1:** architecture 2. Budget architecture 3 in Design C / spare. **Do not** ship architecture 1.

---

## Part 13 — ALU relay count from a 1-bit slice

Functions `ALUCard.evaluate` actually provides: invert_b, ADD/ADC sum+carry, AND, OR, XOR (also via adder), BIT (AND + B6/B7 flags), PASS_A, ASL/LSR/ROL/ROR, decimal nibble adjust when D=1.

| Slice function | Optimistic DPDT | Expected | Conservative | Share poles? |
| --- | --- | --- | --- | --- |
| invert_b (B vs /B from ALU_B complementary) | 1 | 1 | 1 | Uses ALU_B /Q |
| XOR A⊕B′ (sum partial) | 1 | 1 | 2 | — |
| XOR with Cin (sum) | 1 | 1 | 2 | — |
| Carry G/P | 1 | 2 | 2 | Majority vs dedicated G and P |
| AND | 0.5 | 1 | 1 | One pole; OR on the other |
| OR | 0.5 | 0 | 1 | Shared with AND if mux selects pole |
| Shift L/R routing | 0 | 1 | 1 | Byte wiring; 1 DPDT/bit L vs R |
| Result select ADD/LOGIC/SHIFT | 2 | 2 | 3 | 4:1 needs 2; 8:1 needs 3 |
| **Per bit** | **7** | **9** | **13** | |
| **×8 bits** | **56** | **72** | **104** | |

Byte-wide:

| Block | Optimistic | Expected | Conservative |
| --- | --- | --- | --- |
| Z tree | 4 | 4 | 6 |
| N | 0 | 0 | 0 |
| V | 2 | 2 | 4 |
| C_latch storage | 1 | 2 | 2 |
| Cin mux 4:1 | 2 | 2 | 4 |
| BCD +6 hardware | 0 (microcode later) | 8 | 12 |
| **Byte extras** | **9** | **18** | **28** |

**ALU total: optimistic ~65, expected ~90, conservative ~132.**

Rare functions: XOR can be an adder tap; BIT uses AND+wires; PASS_A is result mux selecting A. **Do not** build a subtractor. Decimal: Contiki/BASIC bring-up does not `SED`. **Expected budget keeps 8 DPDT** so D mode is not silently dropped vs `alu.py`.

Result OE (4 DPDT) is counted in Part 3, not again here.

---

## Part 14 — Preserve 6502 behavior

Allowed: fewer microsteps, different physical paths, fused ALU+DST, PC+1 hardware, ADDR_PC, timing classes.

Not allowed: different A/X/Y/SP/P/PC/memory results; 65C02; filling illegal opcodes; skipping abs,X carry; fixing `JMP ($xxFF)`.

| Sequence now | Physical equivalent | Software sees |
| --- | --- | --- |
| PCL→MARL, PCH→MARH, MEM→MDR, MDR→IR, 8-row PC+1 | ADDR_PC, MEM→IR, PC←PC+1 | Next opcode in IR, PC incremented |
| `fetch_byte` | ADDR_PC, MEM→MDR, PC←PC+1 | Operand in MDR, PC incremented |
| `pc_inc` on RTS | PC←PC+1 hardware | PC points at next instruction |
| `xfer(A,ALU_A); alu; xfer(ALU,A)` | optional fuse | A updated, flags as now |

**Emulator changes later (not now):**

1. `isa.FETCH` / `isa.fetch_byte` / `isa.pc_inc` rewritten to the 2-phase sequences (or CW bits `addr_pc` / `pc_inc_hw`).
2. `CW.pack` unused bytes: `TCLASS`, maybe fused DST.
3. `WallClock` / `CPU.step` wait by class.
4. Tests that assert **row counts** updated; tests that assert **architectural state** unchanged.

Do not retarget microcode until experiments 1–6 and 9–10 pass.

---

## Part 15 — Optimized relay budget

### DESIGN A — Minimal (closest to current architecture)

Goal: fewest relays. Silicon bus OE. ALU PC+1. One timing class.

| Block | DPDT |
| --- | --- |
| Storage | 110 |
| Source-enable (HC541) | 0 |
| ALU expected | 90 |
| PC accelerator | 0 |
| Address selection | 0 |
| Fast paths | 0 |
| Control | 4 |
| Miscellaneous | 16 |
| **TOTAL expected** | **~220** |
| Optimistic / conservative | ~185 / ~280 |

Performance: baseline ~30–33 µsteps/ins, ~1.5 IPS at 20 ms.

### DESIGN B — Recommended (v1)

Goal: electromechanical datapath + Option C fetch. Spend ~50–100 relays above Design A on **OE + PC**, not a second ALU.

| Block | DPDT |
| --- | --- |
| Storage | 110 |
| Source-enable (paired) | 55 |
| ALU expected | 90 |
| PC incrementer | 16 |
| Address selection PC/MAR | 8 |
| Fast paths | 0 |
| Control / timing class | 4 |
| Miscellaneous (debug, spare positions) | 32 |
| **TOTAL expected** | **~315** |
| **BOM / comfortable populate** | **~390–450** |
| Conservative (per-bit OE, fat ALU, 24-rel PC+1, grouped carry stuffed) | **~470–520** |

**WHY 450–500 rather than 220 or 800:** 220 only exists if the internal bus goes back to silicon. ~315 is the honest populated count if pairing and 1-relay bits both work. The **450 BOM** is the build envelope: per-bit OE if pairing fails (+~50), conservative ALU (+~20–40), PC+1 isolation (+8), grouped carry (+8–12), unpopulated spares. Crossing **550** stacks an inc helper, ALU bypass muxes, and pessimism. **800** would mean 2-relay bits **and** a second ALU — not justified.

### DESIGN C — Performance

Spend toward **550** only for measured leftovers after B.

| Block | DPDT |
| --- | --- |
| Design B expected | 315 |
| Per-bit OE instead of paired | +50 |
| Grouped 4+4 carry | +12 |
| MDR/A ALU input muxes | +8 |
| Inc/dec helper | +12 |
| Extra PC+1 isolation | +8 |
| **TOTAL expected** | **~405** |
| Conservative stack | **~520–560** |

Predicted extra speed vs B: ~5–10%. **Not** another 2×.

---

## Part 16 — Performance table

**A** = current emulator. **B** = Design B Option C (FETCH 2, fetch_byte 2, hardware PC+1). **C** fuses ALU+DST (−1 on LDA/ADC/INX writeback) and inc helper (−3 on INX/DEX). END still a row.

| Instruction | Design A | Design B | Design C |
| --- | --- | --- | --- |
| NOP | 13 | 3 | 3 |
| LDA # | 27 | 8 | 7 |
| LDA zp | 30 | 11 | 10 |
| LDA abs | 42 | 14 | 13 |
| STA abs | 40 | 12 | 12 |
| ADC # | 28 | 9 | 7 |
| ADC abs | 43 | 16 | 14 |
| INX | 17 | 7 | 4 |
| DEX | 17 | 7 | 4 |
| Branch taken | 33 | 14 | 14 |
| Branch not taken | 24 | 5 | 5 |
| JSR | 54 | ~26 | ~26 |
| RTS | 37 | ~20 | ~20 |
| PHA | 21 | 11 | 11 |
| PLA | 23 | 13 | 12 |

Workload-weighted average µsteps/instruction:

| Workload | A | B | C (approx) |
| --- | --- | --- | --- |
| BASIC PRINT | 30.5 | **12.8** | ~12.0 |
| BASIC FOR | 32.0 | **13.5** | ~12.6 |
| Contiki hello | 30.7 | **13.4** | ~12.5 |
| Contiki boot | 29.9 | **12.9** | ~12.0 |
| Contiki idle | 33.1 | **13.9** | ~13.0 |
| Monitor prompt | 33.0 | **13.3** | ~12.5 |

**IPS (Contiki/BASIC mix ≈ 13 µsteps/ins on B):**

| Timing | Design A (~31 µsteps) | Design B (~13 µsteps) |
| --- | --- | --- |
| Conservative equal 20 ms/row | ~1.6 | ~3.8 |
| Conservative mixed (FAST/MEM 12 ms, ADD 25 ms; after B most rows FAST) | ~1.6 | **~6** |
| Likely bench (FAST 8 ms, ADD 20 ms) | n/a (A still has 50% ADD-class `pc_inc`) | **~8–9** |

Design A cannot use FAST timing on half its rows because those rows **are** ADD (`pc_inc`). That is a second, independent reason PC+1 hardware wins.

---

## Part 17 — Rank optimizations

| Rank | Optimization | Relays | µsteps saved | Frequency | Speedup vs A | Relays per % | Complexity | Recommend? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Dedicated PC incrementer | 16–24 | 7 / fetch | ~2 / ins | ~1.8× | **~0.2** | Med | **Yes** |
| 2 | PC/MAR address select | 8 | 2 / fetch | ~2 / ins | ~1.2× alone; **needed for 2-phase fetch** | ~0.4 with C | Low | **Yes** |
| 3 | Combined fast fetch (1+2) | 24–32 | 10+9×operands | every ins | **~2.3×** | **~0.2** | Med | **Yes (v1)** |
| 4 | Contact/Manchester carry | 0–16 vs coil-ripple | time, not rows | every ADD | can **double ADD-class speed**; after B ADD is rare | — | Med | **Yes** |
| 5 | Variable TCLASS | 0 (silicon) | 0 rows | all FAST rows | ~1.3–1.6× wall time on B | 0 | Low | **Yes** |
| 6 | Fuse ALU+DST in CW | 0–4 | 1 / writeback | after B, ~1/ins | ~5–8% on B | 0 | Low | Yes, microcode later |
| 7 | Grouped 4+4 carry | 8–12 | 0 rows | ADD | small once contact ripple works | high | Med | Design C if bench fails |
| 8 | MDR→ALU mux | 4 | 1 | 46% ins | ~1.5% on A, ~3% on B | ~1.3 | Low | Design C only |
| 9 | A→ALU mux | 4 | 1 | 14% ins | ~0.5% | ~8 | Low | **No** |
| 10 | Inc/dec helper | 10–12 | 3 | 5–14% ins | ~3% on B | ~4 | Med | **No** for v1 |
| 11 | Second ALU | ~90 | — | — | unjustified | — | High | **No** |
| 12 | Silicon bus OE | −55 | 0 | — | 0 | — | Low | Design A only |

---

## Part 18 — Recommended Relay65 v1 architecture

**Choose Design B with Option C fetch, contact-mode ALU carry, variable timing, fused writeback left for a later microcode pass, no second ALU, no INX helper, no A/MDR bypass muxes.**

This is the balance: ~2.3× fewer microsteps where the traces say time is spent; datapath stays relay contacts; relay count stays understandable; BOM sits in the 390–450 band with headroom to 500 if OE pairing or the 1-relay bit fails.

| Item | v1 |
| --- | --- |
| Expected populated DPDT | **~315–360** |
| Planned BOM / spare envelope | **~450** (comfortable &lt;550) |
| Register/bus relays | **165** (110 storage + 55 OE) |
| ALU relays | **~90** expected (65–132 range) |
| PC acceleration | **16** incrementer + **8** address select = **24** |
| Other fast paths | **0** |
| Avg µsteps/instruction (BASIC / Contiki) | **~13** (was ~30–33) |
| BASIC | ~13 µsteps/ins; **~6 IPS** conservative mixed timing; **~8 IPS** likely |
| Contiki | same band; idle loop still branch-heavy but FETCH is 2 rows |
| Conservative relay timing | FAST/MEM 12 ms, LOGIC 15 ms, ADD 30 ms |
| Likely optimized timing | FAST/MEM 8 ms, LOGIC 10 ms, ADD 20 ms |
| Power (5 V, 40 mA class) | Storage 1s: ~2 A typical, ~4 A all-ones architectural bits; ADD peak +ALU coils ~3 A; **plan a 5 V / 10 A coil supply (~50 W)** plus logic PSU. Latching BOM is the power escape hatch. |
| Biggest remaining risks | (1) 1-relay bit hold/release with suppression; (2) bus contention/bounce; (3) contact-carry noise/voltage drop; (4) static coil heat/noise; (5) microcode retarget bugs when FETCH is shortened — mitigated by keeping the current emulator as reference until experiments pass. |

Hard ceiling 800: do not go there. If 1-relay bits fail, 2-relay storage → ~425 populated + envelope **~500–550**, still one ALU, still Design B datapath.

---

## Part 19 — Construction implications (NEW build order)

Do **not** order hundreds of relays until experiments 1–6 pass. Silicon bus buffers may be used on the bench as a **debug tap**, not as the intended CPU source mux.

| # | Experiment | Relays | Success |
| --- | --- | --- | --- |
| 1 | Single stored bit: self-hold, SET, RESET, LOAD=0 retention, LED, diode vs zener release | 1 | Holds 1 for minutes; LOAD 0 then 1 then 0 retains; RESET releases within budgeted ms; no drop-out from bounce |
| 2 | 2-bit DPDT OE onto a dummy bus | 1 storage×2 + 1 OE | Bits appear only when OE=1; Hi-Z when 0; no sneak path |
| 3 | 8-bit register (storage + 4 OE) | 12 | LOAD byte from switches; OE onto bus; lamps match |
| 4 | Two registers, contention | 24 | Φ0 both OE off; Φ1 one-hot; overlapping OE must be **detectably wrong** (current spike or XOR lamps) so we never ship that |
| 5 | 1-bit adder (invert_b, sum, cout) | ~5–9 | Truth table A,B,Cin; no coil-sequenced cin |
| 6 | Carry propagation: force all P=1, inject G at bit 0, watch bit 7 | slice + chain | Cout at MSB without **per-bit extra operate**; settle measured |
| 7 | 4-bit adder | ~30–40 | `$F+$1` and `$0+$0`; time vs 1-bit |
| 8 | 8-bit adder | ALU slice card | Matches `ALUCard` ADD/ADC/invert_b; ADD-class time **&lt;30 ms** conservative |
| 9 | 16-bit PC incrementer | 16 + 16 PC storage | `$00FF`→`$0100`; `$FFFF`→`$0000`; stable during LOAD |
| 10 | PC vs MAR address select | 8 + PC + MAR | SRAM reads PC while MAR holds a different EA; then MAR path for STA |

After 1–4: register cards. After 5–8: ALU card. After 9–10: fetch rewrite is allowed in the emulator. Then IR+EEPROM of `LDA #`, monitor, Contiki.

---

*End of performance-optimized architecture. Reverse-engineering Steps 1–16 above remain the description of the **current** emulator.*
