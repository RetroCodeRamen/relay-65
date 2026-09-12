# Relay-65 hardware implementation (architecture review)

**Status:** review only. This document does not change the emulator, firmware, binaries, or the software-visible 6502 contract. Proposed physical optimizations are **microarchitecture and microcode timing**, not a new ISA.

**Behavioral reference:** the Python emulator under `emulator/relay65/`. Contiki, BASIC, and the monitor already run on it. The physical machine must reproduce that software-visible behavior, not a MOS 6502 die, and not a new ISA.

**Relay accounting:** counts are **physical DPDT relays** (two mechanically linked SPDT poles per package), not contacts. The working cheap-relay class assumed below is a **5 V coil, ~40 mA, non-latching DPDT** with millisecond operate/release (G6K-class in `DESIGN.md` remains a size/footprint reference, not a frozen BOM).

**OLD DESIGN target:** roughly **220 DPDT** by using semiconductor buffers for most internal-bus source selection.

**NEW DESIGN target:** keep an **electromechanical datapath** (storage, routing contacts, ALU, architectural registers, PC, MAR/MDR/IR). Silicon remains allowed for microcode ROM, decode, coil drivers, RAM/ROM/peripherals, and clocks. Preferred total **approximately 450–500 DPDT**; comfortable **under 550**; hard ceiling **800**. Spend ~50–100 extra relays when they cut microcycles enough to raise real IPS.

**Do not optimize for minimum relay count alone.** Order of preference: real execution speed, understandable architecture, electromechanical datapath authenticity, reasonable relay count, buildability, debugging, power, software compatibility.

---

## How to read this document

The emulator is already a **horizontal microcoded 8-bit datapath**: one shared bus, one ALU, registers as OE/LOAD slices, memory only via MAR. Opcode “decoding” is EEPROM lookup of `{IR, uStep}`. That *is* the CPU. A gate-level 6502 clone would be a different machine.

Silicon is allowed for SRAM/ROM, microcode EEPROM, decode, coil drivers, clocks, UART, CF, ESP32, and similar support (`DESIGN.md` §3). Relays must perform architectural storage, the ALU, **and** the routing that moves bytes between those units.

Steps 1–3, 9, 11–12, and 16 reverse-engineer the **current emulator** (still the behavioral reference). Steps 4–8, 10, and 13–15 recorded the **OLD DESIGN** (~220 relays, silicon bus OE, PC through the ALU). Those sections are kept. The **NEW DESIGN** is specified in [Performance-Optimized Physical Architecture](#performance-optimized-physical-architecture).

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
