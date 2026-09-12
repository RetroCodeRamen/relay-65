"""Workload profiler. Observes CPU.step; does not change ISA or microcode."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from relay65.assemble import assemble
from relay65.machine import Machine
from relay65.mmap import ROM_BASE
from relay65.signals import AluOp, Dst, Src


@dataclass
class Profile:
    name: str
    microsteps: int = 0
    instructions: int = 0
    fetches: int = 0  # transitions into FETCH completing an opcode fetch row 0
    fetch_rows: int = 0
    exec_rows: int = 0
    irq_rows: int = 0
    reset_rows: int = 0
    mem_rd: int = 0
    mem_wr: int = 0
    alu_add: int = 0
    alu_logic: int = 0
    alu_shift: int = 0
    alu_pass: int = 0
    alu_a_ld: int = 0
    alu_b_ld: int = 0
    alu_wb: int = 0  # Src.ALU
    dst_pc: int = 0
    dst_sp: int = 0
    dst_a: int = 0
    end_if_taken: int = 0
    pc_to_mar: int = 0  # PCL → MARL (start of fetch / fetch_byte)
    operand_mem_rd: int = 0  # EXEC MEM→MDR
    alu_a_from: Counter = field(default_factory=Counter)
    opcodes: Counter = field(default_factory=Counter)
    src: Counter = field(default_factory=Counter)
    dst: Counter = field(default_factory=Counter)

    def note_cw(self, cpu, cw) -> None:
        self.microsteps += 1
        st = cpu.state
        if st == "FETCH":
            self.fetch_rows += 1
        elif st == "EXEC":
            self.exec_rows += 1
        elif st == "IRQ":
            self.irq_rows += 1
        elif st == "RESET":
            self.reset_rows += 1
        if cw is None:
            return
        self.src[cw.src.name] += 1
        self.dst[cw.dst.name] += 1
        if cw.mem_rd or cw.src == Src.MEM:
            self.mem_rd += 1
        if cw.mem_wr or cw.dst == Dst.MEM:
            self.mem_wr += 1
        if cw.dst == Dst.ALU_A:
            self.alu_a_ld += 1
        if cw.dst == Dst.ALU_B:
            self.alu_b_ld += 1
        if cw.src == Src.ALU:
            self.alu_wb += 1
        if cw.dst in (Dst.PCL, Dst.PCH):
            self.dst_pc += 1
        if cw.dst == Dst.SP:
            self.dst_sp += 1
        if cw.dst == Dst.A:
            self.dst_a += 1
        if cw.alu in (AluOp.ADD, AluOp.ADC):
            self.alu_add += 1
        elif cw.alu in (AluOp.AND, AluOp.OR, AluOp.XOR, AluOp.BIT):
            self.alu_logic += 1
        elif cw.alu in (AluOp.ASL, AluOp.LSR, AluOp.ROL, AluOp.ROR):
            self.alu_shift += 1
        elif cw.alu == AluOp.PASS_A:
            self.alu_pass += 1


def peek_cw(cpu):
    """Read the control word CPU.step will use, without mutating sequencer state."""
    from relay65.signals import CW

    st, u, ir = cpu.state, cpu.ustep, cpu.addr.ir
    store = cpu.store
    if st == "RESET":
        raw = store.word(store.reset, u)
    elif st == "IRQ":
        raw = store.word(store.irq, u)
    elif st == "NMI":
        raw = store.word(store.nmi, u)
    elif st == "FETCH":
        raw = store.word(store.fetch, u)
        if raw is None:
            raw = store.execute_word(ir, 0)
            st = "EXEC"
            u = 0
    else:
        raw = store.execute_word(ir, u)
    if raw is None:
        return st, u, None
    return st, u, CW.unpack(raw)


def attach2(cpu, prof: Profile) -> None:
    from relay65.cpu import CPU
    from relay65.signals import Cond

    inner = getattr(cpu, "_raw_step", None)
    if inner is None:
        inner = CPU.step.__get__(cpu, CPU)
        cpu._raw_step = inner

    def step() -> None:
        if cpu.halted:
            inner()
            return
        st0, u0, cw = peek_cw(cpu)
        ir = cpu.addr.ir
        inner()
        if cw is None:
            return
        prof.microsteps += 1
        if st0 == "FETCH":
            prof.fetch_rows += 1
            if u0 == 0:
                prof.fetches += 1
        elif st0 == "EXEC":
            prof.exec_rows += 1
        elif st0 == "IRQ":
            prof.irq_rows += 1
        elif st0 == "RESET":
            prof.reset_rows += 1
        prof.src[cw.src.name] += 1
        prof.dst[cw.dst.name] += 1
        if cw.mem_rd or cw.src == Src.MEM:
            prof.mem_rd += 1
        if cw.mem_wr or cw.dst == Dst.MEM:
            prof.mem_wr += 1
        if cw.src == Src.PCL and cw.dst == Dst.MARL:
            prof.pc_to_mar += 1
        if st0 == "EXEC" and (cw.mem_rd or cw.src == Src.MEM) and cw.dst == Dst.MDR:
            prof.operand_mem_rd += 1
        if cw.dst == Dst.ALU_A:
            prof.alu_a_ld += 1
            prof.alu_a_from[cw.src.name] += 1
        if cw.dst == Dst.ALU_B:
            prof.alu_b_ld += 1
        if cw.src == Src.ALU:
            prof.alu_wb += 1
        if cw.dst in (Dst.PCL, Dst.PCH):
            prof.dst_pc += 1
        if cw.dst == Dst.SP:
            prof.dst_sp += 1
        if cw.dst == Dst.A:
            prof.dst_a += 1
        if cw.alu in (AluOp.ADD, AluOp.ADC):
            prof.alu_add += 1
        elif cw.alu in (AluOp.AND, AluOp.OR, AluOp.XOR, AluOp.BIT):
            prof.alu_logic += 1
        elif cw.alu in (AluOp.ASL, AluOp.LSR, AluOp.ROL, AluOp.ROR):
            prof.alu_shift += 1
        elif cw.alu == AluOp.PASS_A:
            prof.alu_pass += 1
        if cw.end_if != Cond.NEVER and cpu.ustep == 0:
            prof.end_if_taken += 1
        if st0 == "EXEC" and cpu.state in ("FETCH", "IRQ", "NMI"):
            prof.instructions += 1
            prof.opcodes[ir] += 1

    cpu.step = step  # type: ignore


def boot_rom(m: Machine) -> None:
    rom = assemble(
        Path(__file__).resolve().parent.parent.joinpath("rom/monitor.s").read_text(),
        default_origin=ROM_BASE,
    )
    m.load_image(rom.origin, rom.data)


def run_until(m: Machine, pred, limit: int) -> None:
    for _ in range(limit):
        m.step()
        if m.cpu.halted:
            break
        if pred(m):
            break


def summarize(p: Profile) -> str:
    n = max(p.microsteps, 1)
    ins = max(p.instructions, 1)
    lines = [
        f"## {p.name}",
        f"microsteps={p.microsteps} instructions={p.instructions} "
        f"avg_µsteps/ins={p.microsteps / ins:.2f}",
        f"FETCH rows={p.fetch_rows} ({100 * p.fetch_rows / n:.1f}%) "
        f"EXEC={p.exec_rows} ({100 * p.exec_rows / n:.1f}%) "
        f"opcode fetches={p.fetches}",
        f"mem_rd={p.mem_rd} ({100 * p.mem_rd / n:.1f}%) mem_wr={p.mem_wr}",
        f"ALU add/adc={p.alu_add} ({100 * p.alu_add / n:.1f}%) "
        f"logic={p.alu_logic} shift={p.alu_shift} pass={p.alu_pass}",
        f"ALU_A ld={p.alu_a_ld} ALU_B ld={p.alu_b_ld} ALU writeback={p.alu_wb} "
        f"({100 * p.alu_wb / n:.1f}%)",
        f"DST PC={p.dst_pc} SP={p.dst_sp} A={p.dst_a} end_if_taken={p.end_if_taken}",
        f"PCL→MARL={p.pc_to_mar} (opcode fetches={p.fetches}; extra PC-address copies≈{p.pc_to_mar - p.fetches})",
        f"EXEC MEM→MDR={p.operand_mem_rd} (operand + data + stack reads)",
        f"ALU_A sources: " + ", ".join(f"{k}={v}" for k, v in p.alu_a_from.most_common()),
        f"PC+1 µsteps (8×PCL→MARL, approx, includes RTS extra)={8 * p.pc_to_mar} "
        f"({100 * 8 * p.pc_to_mar / n:.1f}%) — overestimates if some PCL→MARL are not followed by pc_inc",
        "top opcodes:",
    ]
    names = {
        0xA5: "LDA zp",
        0xA9: "LDA #",
        0xAD: "LDA abs",
        0x85: "STA zp",
        0x8D: "STA abs",
        0x65: "ADC zp",
        0x69: "ADC #",
        0xE8: "INX",
        0xCA: "DEX",
        0xC8: "INY",
        0x88: "DEY",
        0xD0: "BNE",
        0xF0: "BEQ",
        0x10: "BPL",
        0x30: "BMI",
        0x90: "BCC",
        0xB0: "BCS",
        0x4C: "JMP",
        0x20: "JSR",
        0x60: "RTS",
        0x48: "PHA",
        0x68: "PLA",
        0xEA: "NOP",
        0xBD: "LDA abs,X",
        0xB1: "LDA (zp),Y",
        0x91: "STA (zp),Y",
        0xAA: "TAX",
        0xA8: "TAY",
        0x8A: "TXA",
        0x98: "TYA",
        0xE0: "CPX #",
        0xC9: "CMP #",
        0xC5: "CMP zp",
        0x29: "AND #",
        0x09: "ORA #",
        0x18: "CLC",
        0x38: "SEC",
        0xB5: "LDA zp,X",
        0x95: "STA zp,X",
        0xAD: "LDA abs",
        0xA0: "LDY #",
        0xA2: "LDX #",
        0x86: "STX zp",
        0x84: "STY zp",
        0x24: "BIT zp",
        0xC6: "DEC zp",
        0xE6: "INC zp",
        0x0A: "ASL A",
        0x4A: "LSR A",
        0x2A: "ROL A",
        0x6A: "ROR A",
        0x78: "SEI",
        0x58: "CLI",
        0x08: "PHP",
        0x28: "PLP",
        0x40: "RTI",
        0x6C: "JMP ind",
        0x00: "BRK",
        0xC0: "CPY #",
        0xE4: "CPX zp",
        0xD9: "CMP abs,Y",
        0xF9: "SBC abs,Y",
        0xE9: "SBC #",
        0x75: "ADC zp,X",
        0x7D: "ADC abs,X",
        0x1D: "ORA abs,X",
        0x3D: "AND abs,X",
        0xBC: "LDY abs,X",
        0xBE: "LDX abs,Y",
        0x99: "STA abs,Y",
        0x9D: "STA abs,X",
        0x81: "STA (zp,X)",
        0xA1: "LDA (zp,X)",
        0x11: "ORA (zp),Y",
        0x71: "ADC (zp),Y",
        0xD1: "CMP (zp),Y",
        0x51: "EOR (zp),Y",
        0x45: "EOR zp",
        0x05: "ORA zp",
        0x25: "AND zp",
        0xC4: "CPY zp",
        0xE6: "INC zp",
        0xB9: "LDA abs,Y",
        0x19: "ORA abs,Y",
        0x39: "AND abs,Y",
        0x79: "ADC abs,Y",
        0xF1: "SBC (zp),Y",
        0x55: "EOR zp,X",
        0x15: "ORA zp,X",
        0x35: "AND zp,X",
        0xD5: "CMP zp,X",
        0xB4: "LDY zp,X",
        0xB6: "LDX zp,Y",
        0x94: "STY zp,X",
        0x96: "STX zp,Y",
        0x88: "DEY",
        0xC8: "INY",
        0xCA: "DEX",
        0xE8: "INX",
        0xBA: "TSX",
        0x9A: "TXS",
        0x2C: "BIT abs",
        0xCE: "DEC abs",
        0xEE: "INC abs",
        0x0E: "ASL abs",
        0x4E: "LSR abs",
        0x2E: "ROL abs",
        0x6E: "ROR abs",
        0x26: "ROL zp",
        0x66: "ROR zp",
        0x06: "ASL zp",
        0x46: "LSR zp",
        0xE5: "SBC zp",
        0xC5: "CMP zp",
        0xD8: "CLD",
        0xF8: "SED",
        0xB8: "CLV",
    }
    for op, c in p.opcodes.most_common(15):
        lines.append(f"  ${op:02X} {names.get(op, '?'):12} {c:7} ({100 * c / ins:.1f}%)")
    lines.append("top SRC: " + ", ".join(f"{k}={v}" for k, v in p.src.most_common(8)))
    lines.append("top DST: " + ", ".join(f"{k}={v}" for k, v in p.dst.most_common(8)))
    # time buckets
    pc_inc_rows = 8 * p.fetches  # every FETCH includes pc_inc; operand fetch_byte also
    # fetch_byte also in EXEC: mem_rd during EXEC that are operand fetches approx
    lines.append(
        f"approx FETCH-included PC+1 rows (8*opcode_fetches)={8 * p.fetches} "
        f"({100 * 8 * p.fetches / n:.1f}% of all µsteps)"
    )
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = []

    def make(name: str) -> tuple[Machine, Profile]:
        m = Machine()
        boot_rom(m)
        p = Profile(name)
        attach2(m.cpu, p)
        return m, p

    # Monitor to prompt
    m, p = make("monitor to prompt")
    m.reset()
    run_until(m, lambda x: b">" in bytes(x.uart.tx_log) and b"monitor" in bytes(x.uart.tx_log), 300_000)
    out.append(summarize(p))

    hello = root / "software/contiki/hello-world.bin"
    if hello.exists():
        m, p = make("Contiki hello-world")
        m.load_ram(0x0200, hello.read_bytes())
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        run_until(
            m,
            lambda x: b"Hello, world" in bytes(x.uart.tx_log)
            and b"Contiki on Relay-65" in bytes(x.uart.tx_log),
            500_000,
        )
        out.append(summarize(p))

    console = root / "software/contiki/console.bin"
    if console.exists():
        m, p = make("Contiki console boot")
        m.load_ram(0x0200, console.read_bytes())
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        run_until(m, lambda x: b"console ready" in bytes(x.uart.tx_log), 800_000)
        out.append(summarize(p))

        # idle: extra steps after ready
        p2 = Profile("Contiki console idle 100k µsteps")
        attach2(m.cpu, p2)
        for _ in range(100_000):
            m.step()
        out.append(summarize(p2))

        m.uart.push_rx(b"basic\n")
        p3 = Profile("BASIC enter + PRINT 1+2")
        attach2(m.cpu, p3)
        run_until(m, lambda x: b"READY" in bytes(x.uart.tx_log), 1_500_000)
        m.uart.push_rx(b"PRINT 1+2\n")
        run_until(m, lambda x: b"3" in bytes(x.uart.tx_log)[-20:], 1_500_000)
        out.append(summarize(p3))

        m.uart.push_rx(b"10 FOR I=1 TO 10\n")
        run_until(m, lambda x: True, 50_000)
        # consume line
        for _ in range(200_000):
            m.step()
            if b"10 FOR" in bytes(m.uart.tx_log)[-80:]:
                break
        m.uart.push_rx(b"20 PRINT I\n")
        for _ in range(200_000):
            m.step()
        m.uart.push_rx(b"30 NEXT I\n")
        for _ in range(200_000):
            m.step()
        p4 = Profile("BASIC RUN FOR 1 TO 10 PRINT")
        attach2(m.cpu, p4)
        m.uart.push_rx(b"RUN\n")
        for _ in range(400_000):
            m.step()
        out.append(summarize(p4))

    text = "\n\n".join(out)
    Path("/tmp/relay65_profile.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
