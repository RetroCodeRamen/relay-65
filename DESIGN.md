# Relay-65

**Luggable Computer — Design Plan & Philosophy**

*Working Draft v0.1 · September 6, 2026*

Primary software goals: bare-metal monitor → Contiki (no IP stack) → FUZIX.
TCP/Wi-Fi lives on the ESP32 card, not on the 6502.

A portable electromechanical computer whose 6502-compatible machine instructions are physically executed by relays, while modern semiconductor support hardware is used where it improves practicality without hiding the CPU.

## 1. Project Vision

**Relay-65 is a modular, luggable relay computer built around a software-compatible 6502-class CPU.** The CPU datapath, architectural state, instruction execution, and arithmetic should be visibly and audibly electromechanical. Semiconductor components are allowed for memory, microcode storage, drivers, networking, storage, and other support functions when implementing those functions in relays would add size and complexity without improving the core demonstration.

> **Design rule:** The project succeeds when normal 6502 software executes because relay logic performs the CPU work—not because a hidden microcontroller emulates the CPU.

The machine should be more than a single-purpose exhibit. It should be a small computer platform that can accept interchangeable processor cards, peripheral cards, and future expansion hardware. Its modularity should make it practical to build, diagnose, modify, and transport.

## 2. Design Philosophy

**Relays are expensive; cycles are cheap.** Prefer reusing a small amount of relay hardware over duplicating hardware purely to save cycles. Additional microcycles are acceptable when they materially reduce relay count, wiring, board area, and failure points.

**Do not optimize slowness into unusability.** A microcoded design should still spend relays on operations that happen constantly. If an added hardware block substantially improves nearly every instruction—such as efficient program-counter handling—it deserves serious consideration.

**Keep the CPU honest.** External hardware may offload networking, video timing, storage protocols, or memory banking, but it must not fetch and execute 6502 instructions on behalf of the relay CPU.

**Make every subsystem replaceable.** The CPU is divided into functional cards on a passive backplane. No single monolithic PCB should contain the entire machine.

**Design for observation and debugging.** Manual clocking, status LEDs/test points, bus visibility, card isolation, and deterministic timing are requirements rather than luxuries.

**Reliability beats theoretical speed.** Mechanical settling time, contact bounce, inductive noise, power distribution, and connector quality should be treated as first-class architectural constraints.

**Expansion is part of the computer.** The backplane should reserve general-purpose slots for future video, communications, storage, sound, instrumentation, or experimental cards.

## 3. What Counts as a Relay Computer?

For this project, the defining boundary is the CPU instruction path. The following functions are intended to be relay-based:

- Architectural registers used directly by the 6502-compatible instruction set.
- The principal 8-bit arithmetic/logic datapath.
- Bus switching/routing that moves CPU data among relay-based functional units.
- Instruction-level sequencing effects that directly cause relay CPU operations.
- Status/condition generation where practical and architecturally meaningful.

The following functions may be semiconductor-based without violating the project philosophy:

- Microcode ROM/EEPROM and microstep counters.
- Relay coil driver transistors or MOSFETs and flyback protection.
- SRAM, ROM/Flash, bank-selection latches, and address-decode support.
- CompactFlash (8-bit IDE) storage interfaces.
- Ethernet, LoRa, UART, USB, video, audio, RTC, and similar peripheral controllers.
- Debug interfaces, test instrumentation, clock generation, and power regulation.

> **Design rule:** Peripheral coprocessors may be fast and modern; the relay CPU must remain the component that interprets and executes the program’s 6502 machine instructions.

## 4. Baseline CPU Architecture

The baseline target is a documented 6502-compatible instruction set implemented as a deliberately slow microcoded relay CPU. Exact cycle compatibility with an NMOS 6502 is not a first-release requirement; software-visible behavior is more important than reproducing every internal timing quirk.

| Element | Preferred implementation | Reason |
| --- | --- | --- |
| A accumulator | Relay | Core architectural state; heavily used. |
| X register | Relay | Core architectural state. |
| Y register | Relay | Core architectural state. |
| Stack pointer | Relay | Core architectural state; may share ALU for increment/decrement. |
| Processor status | Relay / mixed | Flags should reflect relay datapath results; implementation may use support logic where justified. |
| Program counter | Relay | 16-bit architectural state. Dedicated increment assistance remains under evaluation. |
| Instruction register | Relay or relay-visible latch | Should make the currently executing opcode observable. |
| Temporary/MDR/MAR state | Relay or mixed | Use only where needed to simplify sequencing and bus access. |
| 8-bit ALU | Relay | Reusable arithmetic/logic block; central hardware investment. |
| Microcode store | EEPROM/Flash | Horizontal control word preferred to reduce decoder relays. |
| Microstep sequencing | Semiconductor | Does not execute software; sequences relay datapath operations. |

## 5. Microcode Strategy

The control unit should use microcode primarily to trade time for less electromechanical hardware. The preferred starting point is a wide, mostly horizontal control word so EEPROM outputs can directly request useful CPU actions rather than requiring large relay decoder trees.

**Example conceptual micro-operation:**

```
A_OUT    → BUS
ALU_B_IN ← BUS
MEM_OUT  → BUS
ALU_A_IN ← BUS
ALU_ADD
A_LOAD   ← ALU
FLAGS_LOAD
```

This is intentionally not a final signal definition. The final microinstruction format will be created only after the datapath and backplane signals are frozen.

> **Design rule:** Use microcode to eliminate duplicate hardware, but avoid serializing universally common operations so aggressively that normal software becomes needlessly unusable.

> **Open decision:** Whether the program counter receives a dedicated relay incrementer, a partial increment assist, or always reuses the main ALU.

## 6. Modular Card-Cage Architecture

The computer will be divided into functional boards plugged into a common backplane. This modularity is central to the design—not just a packaging choice. Cards should be individually testable and replaceable.

| Card | Primary responsibility |
| --- | --- |
| Control / Microcode | Microcode EEPROMs, microstep logic, clock/step/reset functions, control-line drivers. |
| Register Bank | A, X, Y, stack pointer, status, and selected temporary state. |
| ALU | 8-bit arithmetic/logic operations, carry path, flag generation, shifts as appropriate. |
| Program Counter / Address | PC state, address-generation support, MAR/bus interface, optional increment assist. |
| Memory / System | SRAM, ROM/boot support, bank switching, memory map decode. |
| I/O / Console | Initial UART/terminal functions and low-level bring-up interfaces. |

> **Design rule:** The backplane should be electrically passive whenever practical. Intelligence belongs on cards, not hidden in the backplane.

A mechanically robust multi-pin connector such as a DIN 41612 / Eurocard-style connector is a leading concept because it offers many contacts, good retention, and a replaceable connector interface. The actual connector and board dimensions are not yet frozen.

> **Open decision:** Final card format, connector family, connector pin count, slot spacing, and backplane dimensions.

## 7. Internal Bus Philosophy

The backplane should expose a purpose-built internal CPU bus rather than blindly reproducing the external pinout of a 6502. Internal signals may include a shared 8-bit datapath, address paths, CPU control signals, clock phases, and card-specific selects.

**Conceptual internal datapath**

```
 A ─┐
 X ─┤
 Y ─┤
SP ─┼── 8-bit internal bus ── ALU ── result bus
PC ─┤
MDR─┤
MEM─┘
```

Mechanical contacts require deterministic settling. Bus operations should therefore be phased so that a source is selected, contacts are allowed to settle, and only then is the destination latched. The exact timing will be measured from real relay hardware rather than assumed from datasheet maxima alone.

**Illustrative bus phase sequence**

```
1. Release prior source
2. Select new source
3. Allow operate/bounce settling interval
4. Sample or latch destination
5. Release / advance microstep
```

## 8. Memory Model

The physical CPU exposes a 16-bit 6502 address space. The first hardware milestone should be able to run conventional 64 KiB 6502 software. Additional physical SRAM and a bank-switching mechanism should be designed in so FUZIX can later use a larger memory model.

- Base logical address space: 64 KiB.
- Physical RAM target: **512 KiB** (32 × 16 KiB pages). Contiki still uses `$C010` on the `$8000` window. FUZIX uses `$C018–$C01B`.
- Boot/monitor ROM mapped into the 6502 address space with a mechanism to expose RAM where required.
- Banking implemented with semiconductor latches/decoders; the relay CPU accesses memory normally through its address/data interface.
- Memory banking register(s) should be simple enough to port into FUZIX platform code.

> **Frozen:** four 16 KiB page registers at `$C018–$C01B`; Contiki `$C010` aliases page 2. Slot decode: `$C100` CF, `$C200` ESP32; `$C300+` is SRAM in v0.1 (later slots would steal that decode).

## 9. Expansion Bus

The chassis should include several general-purpose expansion slots in addition to the CPU cards. Expansion hardware should see a stable machine-level interface rather than private microcode control signals.

| Signal group | Purpose |
| --- | --- |
| D0–D7 | 8-bit system data bus |
| A0–A15 | 16-bit logical address bus |
| READ / WRITE | Peripheral transfer direction/control |
| RESET | System reset |
| IRQ / NMI | Interrupt capability |
| SLOT SELECT | Dedicated per-slot selection to simplify card decode |
| BUS REQUEST / GRANT | Reserved for future DMA/bus mastering |
| CLOCK / timing reference | Optional timing reference; peripherals should not depend on internal microsteps |
| +5 V / +12 V / GND | Logic and relay/peripheral power, with multiple power/ground contacts |

The preferred software model is memory-mapped I/O with a small address window assigned to each slot. Dedicated slot-select lines can be generated centrally so an expansion card does not need to decode the entire address bus.

> **Design rule:** Reserve DMA/bus-mastering signals now even if version 1 firmware and hardware do not use them.

## 10. Example Expansion Cards

| Possible card | Concept |
| --- | --- |
| Terminal / video card | Character terminal output, local framebuffer, VGA/HDMI generation, keyboard input. Video timing is performed locally rather than by relays. |
| Graphics coprocessor | Optional command-driven drawing/blitting engine with local RAM; could later use DMA. |
| LoRa radio | SPI/UART radio module presented to the CPU as simple registers and interrupts. |
| Ethernet | **Frozen: ESP32 mailbox `$C200`.** TCP/Wi-Fi on the card, not uIP on the 6502. |
| Storage | CompactFlash, 8-bit IDE task file at `$C100`. |
| UART / serial | Console, debugging, terminal connection, and simple file transfer. |
| Sound | PSG/synthesizer or DAC-based audio controlled through registers. |
| GPIO / instrumentation | Digital I/O, ADC/DAC, front-panel switches, sensors, or lab interfaces. |
| Debug card | Bus monitor, trace capture, logic analyzer, or microcode-state display. |

## 11. Software Targets

Software will be brought up in layers so that each hardware milestone provides a useful proof of progress.

| Stage | Purpose |
| --- | --- |
| 6502 functional tests | Validate instruction semantics and identify CPU bugs before an operating system is attempted. |
| Monitor ROM | Memory examine/deposit, register display, single-step support, load/save, and peripheral tests. |
| Simple standalone programs / BASIC | Exercise the machine as a conventional 6502 system. |
| Contiki (no uIP) | First OS on the UART: console, BASIC, prove the CPU. Networking is **not** Contiki/uIP on the 6502. |
| FUZIX | Stretch OS. cc65 `--cpu 6502`, 512 KiB paged SRAM, CF root. TCP stays on the ESP32 mailbox. |

> **Design rule:** The initial CPU should implement documented 6502 behavior accurately enough for standard binaries; undocumented opcodes and exact dead-cycle behavior are not required for version 1.

## 12. Physical and Electrical Philosophy

The entire machine should fit into a transportable luggable enclosure. The design should favor several dense, serviceable cards rather than one enormous relay panel. Noise, heat, and coil current must be planned from the start.

- Current relay candidate class: miniature low-power DPDT signal/telecom relays; Omron G6K-class parts are a working reference, not yet a frozen BOM item.
- Prefer a relay supply around 12 V if the selected coil family makes that advantageous for distribution current.
- Use local transistor/MOSFET coil drivers; do not route coil current through logic/control traces across the backplane.
- Provide flyback suppression at every inductive load.
- Provide local bulk capacitance and logic decoupling on every card.
- Use multiple connector pins for power and ground, especially relay power.
- Design airflow and service access around realistic worst-case coil dissipation.
- Keep front-panel manual clock, reset, halt, and diagnostic controls available during development.

> **Open decision:** Exact relay model and coil voltage after bench testing switching time, bounce, acoustic behavior, availability, cost, contact life, and driver requirements.

## 13. Development and Test Strategy

The system should be built in independently testable layers. Each new card should have a standalone test method before it becomes a dependency for the next card.

1. Build a relay characterization fixture: measure operate time, release time, bounce, coil current, contact resistance, and safe clock/phase timing.
2. Freeze backplane electrical levels and signal ownership rules.
3. Prototype one 8-bit relay register plus bus interface and manual load/output controls.
4. Build and exhaustively test the 8-bit ALU independently.
5. Integrate register + ALU cards on the backplane and execute manual micro-operations.
6. Add program counter/address card and memory interface.
7. Add control/microcode card and execute a minimal opcode subset.
8. Run a 6502 functional test suite in simulation, then on hardware.
9. Bring up ROM monitor and serial console.
10. Add expansion bus cards: storage and Ethernet/terminal first.
11. Port or adapt Contiki platform support.
12. Finalize banked-memory support and attempt FUZIX.

## 14. Project Design Rules — v0.1

- CPU program instructions are executed by relay logic.
- The backplane is modular and preferably passive.
- CPU cards and expansion cards are separate conceptual interfaces even if they share one physical backplane.
- Expansion slots expose stable machine-level bus signals, not private microcode details.
- Microcode ROM may be semiconductor-based and should favor wide/direct control to avoid relay decoding overhead.
- SRAM/ROM and banking may be semiconductor-based.
- Networking, video, storage, LoRa, audio, and other peripherals may use modern electronics.
- Speed optimizations must justify their relay count and wiring cost.
- Operations used by nearly every instruction deserve more optimization than rare operations.
- Contact settling and electrical noise are part of CPU timing design.
- Every board should have a standalone test strategy.
- Expansion capability and reserved signals should be designed before the backplane is frozen.

Emulator and hardware share one blueprint: [`docs/RELAY-CPU.md`](docs/RELAY-CPU.md).
v0.1 freezes a single internal bus, one reused ALU (including PC/SP), and the
memory map. The Python CPU walks EEPROM control words; it does not interpret
opcodes in software.

## 15. Major Open Decisions

- Exact relay part and coil voltage.
- Exact card dimensions and connector standard.
- Number of CPU slots and number of general expansion slots.
- Physical orientation: vertical card cage, horizontal stack, or hybrid service tray.
- Internal bus topology: **frozen v0.1 — one shared 8-bit bus** (see docs/RELAY-CPU.md).
- Program-counter increment hardware: **frozen v0.1 — reuse the 8-bit ALU**; dedicated +1 is a later microcode swap.
- Exact ALU function set: **ADD/ADC, AND, OR, XOR, PASS, ASL/LSR/ROL/ROR, BIT**; shifts live in the ALU.
- Which temporary registers are true relay registers versus semiconductor support latches: **IR, MDR, MAR, T, ALU_A, ALU_B are relay-visible latches**.
- Backplane electrical signaling levels and buffering strategy.
- Microcode control-word width and EEPROM organization.
- Clock-phase timing and manual/single-step implementation.
- Memory map, ROM placement, FUZIX banking strategy, and expansion-slot I/O windows: **v0.1 map frozen in emulator/relay65/mmap.py**.
- Interrupt-controller approach and number of physical interrupt lines.
- DMA arbitration details for future expansion cards.
- First terminal/video solution.
- First network card: **ESP32 in slot 1 (`$C200`)**. Frozen: **TCP/Wi-Fi on
  the ESP32**, not on the 6502 (no uIP/FUZIX IP stack as the production path).
  The 6502 sees a mailbox: listen/accept on port 80, read request, write
  response from RAM or CF, close. Slot 0 (`$C100`) is CompactFlash. The ESP32
  must not fetch or execute 6502 instructions.

## 16. Immediate Next Design Artifacts

v0.1 of items 1–3 now lives in the emulator, which is meant to be the
schematic-level contract:

1. Backplane / memory map — `emulator/relay65/mmap.py`, `docs/RELAY-CPU.md`
2. Datapath — `registers.py`, `alu.py`, `address.py` (one bus, one ALU)
3. Micro-ops — `signals.py` + `isa.py` + packed `eeprom.py` (8-byte rows)
4. Register card schematic — still to draw from the 8-bit slice in `registers.py`
5. Relay characterization — not started; `CPU.step()` walks Φ0/Φ1/Φ2, `WallClock` still uses placeholder ms

> **Design rule:** Do not change software-visible behavior in hardware without
> changing the emulator first. Dedicated PC+1, if added, is a microcode swap.

## 17. Technical References and Inspiration

These references are useful starting points rather than requirements to clone directly.

- [C74-6502 Internals](https://c74project.com/c74-6502-internals/) — complete discrete-TTL 6502 architecture, schematics, microcode, and project files.
- [C74-6502 Microcode](https://c74project.com/microcode/) — control-ROM organization and microinstruction documentation.
- [FUZIX repository](https://github.com/EtchedPixels/FUZIX) — current project source and build notes; 6502 builds use cc65.
- [FUZIX 6502 wiki notes](https://github.com/EtchedPixels/FUZIX/wiki/Home) — 6502 platform status, banking expectations, and recommended memory.
- [cc65](https://github.com/cc65/cc65) — compiler, assembler, linker, libraries, and simulator for 65(C)02 systems.
- [Contiki OS repository](https://github.com/contiki-os/contiki) — constrained-device operating system and networking platform.

---

*Document intent: capture the architecture we have agreed on, make assumptions explicit, and prevent future subsystem decisions from quietly changing the core goal of the machine.*
