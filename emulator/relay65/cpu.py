"""Control / CPU sequencer: FETCH page + execute EEPROM, Φ0/Φ1/Φ2 microsteps.

This is not a 6502 opcode interpreter. It clocks packed EEPROM words onto
the same SRC/DST/ALU lines the Control card will drive.
"""

from __future__ import annotations

from .address import AddressCard
from .alu import ALUCard
from .eeprom import ControlStore
from .memory import MemoryCard
from .registers import RegisterCard
from .signals import (
    FB,
    FU,
    FI,
    AluOp,
    CW,
    Cond,
    Dst,
    FLG_N,
    FLG_Z,
    FN,
    FV,
    FC,
    FZ,
    Src,
)


class CPU:
    def __init__(self, memory: MemoryCard) -> None:
        self.memory = memory
        self.reg = RegisterCard()
        self.alu = ALUCard()
        self.addr = AddressCard()
        self.store = ControlStore.from_isa()
        self.state = "RESET"
        self.ustep = 0
        self.phi = 0
        self.oe_src = Src.NONE
        self.halted = False
        self.microcycles = 0
        self.instructions = 0
        self.last_bus = 0
        self.nmi_edge = False
        self._mem_addr = 0

    @property
    def a(self) -> int:
        return self.reg.a

    @property
    def x(self) -> int:
        return self.reg.x

    @property
    def y(self) -> int:
        return self.reg.y

    @property
    def sp(self) -> int:
        return self.reg.sp

    @property
    def p(self) -> int:
        return self.reg.p

    @property
    def pc(self) -> int:
        return self.addr.pc

    @pc.setter
    def pc(self, value: int) -> None:
        self.addr.pc = value

    def reset(self) -> None:
        self.reg.reset_status()
        self.halted = False
        self.state = "RESET"
        self.ustep = 0
        self.phi = 0
        self.oe_src = Src.NONE
        self.microcycles = 0
        self.instructions = 0

    def snapshot(self) -> str:
        return (
            f"A={self.reg.a:02X} X={self.reg.x:02X} Y={self.reg.y:02X} "
            f"SP={self.reg.sp:02X} PC={self.addr.pc:04X} P={self.reg.p:02X} "
            f"IR={self.addr.ir:02X} MAR={self.addr.mar:04X} {self.state} "
            f"u={self.ustep} Φ{self.phi}"
        )

    def step(self) -> None:
        """One EEPROM row: Φ0 release, Φ1 OE+ALU, Φ2 LOAD. Then idle OE off."""
        if self.halted:
            return
        self.phi = 0
        self.oe_src = Src.NONE
        cw = self._current()
        if cw is None:
            self.halted = True
            return
        if self._cond(cw.end_if):
            self.phi = 2
            self.memory.timer.on_phi2()
            self._end_instruction()
            self.microcycles += 1
            return
        self.phi = 1
        self.oe_src = cw.src
        self._phi1(cw)
        self.phi = 2
        self._phi2(cw)
        self.oe_src = Src.NONE
        self.memory.timer.on_phi2()
        self.microcycles += 1
        if cw.end:
            self._end_instruction()
            return
        self.ustep += 1

    def step_instruction(self) -> None:
        start = self.instructions
        while not self.halted and self.instructions == start:
            self.step()

    def _end_instruction(self) -> None:
        if self.state == "EXEC":
            self.instructions += 1
        if self.state in ("IRQ", "NMI"):
            self.state = "FETCH"
            self.ustep = 0
            return
        if self.nmi_edge:
            self.nmi_edge = False
            self.state = "NMI"
            self.ustep = 0
            return
        if self.memory.timer.irq_line and not (self.reg.p & FI):
            self.state = "IRQ"
            self.ustep = 0
            return
        self.state = "FETCH"
        self.ustep = 0

    def _current(self) -> CW | None:
        if self.state == "RESET":
            raw = self.store.word(self.store.reset, self.ustep)
        elif self.state == "IRQ":
            raw = self.store.word(self.store.irq, self.ustep)
        elif self.state == "NMI":
            raw = self.store.word(self.store.nmi, self.ustep)
        elif self.state == "FETCH":
            raw = self.store.word(self.store.fetch, self.ustep)
            if raw is None:
                self.state = "EXEC"
                self.ustep = 0
                return self._current()
        else:
            raw = self.store.execute_word(self.addr.ir, self.ustep)
        if raw is None:
            return None
        return CW.unpack(raw)

    def _cond(self, cond: Cond) -> bool:
        p = self.reg.p
        if cond == Cond.NEVER:
            return False
        if cond == Cond.ALWAYS:
            return True
        if cond == Cond.Z:
            return bool(p & FZ)
        if cond == Cond.NZ:
            return not (p & FZ)
        if cond == Cond.C:
            return bool(p & FC)
        if cond == Cond.NC:
            return not (p & FC)
        if cond == Cond.N:
            return bool(p & FN)
        if cond == Cond.NN:
            return not (p & FN)
        if cond == Cond.V:
            return bool(p & FV)
        if cond == Cond.NV:
            return not (p & FV)
        return False

    def _drive(self, cw: CW) -> int:
        src = cw.src
        r, a = self.reg, self.addr
        if src == Src.NONE:
            return 0
        if src == Src.A:
            return r.a
        if src == Src.X:
            return r.x
        if src == Src.Y:
            return r.y
        if src == Src.SP:
            return r.sp
        if src == Src.P:
            return (r.p | FU | cw.p_or) & 0xFF
        if src == Src.PCL:
            return a.pcl
        if src == Src.PCH:
            return a.pch
        if src == Src.MDR:
            return a.mdr
        if src == Src.T:
            return r.t
        if src == Src.MARL:
            return a.marl
        if src == Src.MARH:
            return a.marh
        if src == Src.CONST:
            return cw.const & 0xFF
        if src == Src.M7EXT:
            return 0xFF if a.mdr & 0x80 else 0x00
        if src == Src.ALU:
            return self.alu.result
        if src == Src.MEM:
            return self.memory.read(self._mem_addr)
        return 0

    def _get8(self, dst: Dst) -> int:
        r, a = self.reg, self.addr
        if dst == Dst.A:
            return r.a
        if dst == Dst.X:
            return r.x
        if dst == Dst.Y:
            return r.y
        if dst == Dst.SP:
            return r.sp
        if dst == Dst.T:
            return r.t
        if dst == Dst.MARL:
            return a.marl
        if dst == Dst.MARH:
            return a.marh
        if dst == Dst.MDR:
            return a.mdr
        if dst == Dst.P:
            return r.p
        return 0

    def _apply_nz(self, value: int, mask: int) -> None:
        p = self.reg.p
        if mask & FLG_N:
            p = (p & ~FN) | (FN if value & 0x80 else 0)
        if mask & FLG_Z:
            p = (p & ~FZ) | (FZ if (value & 0xFF) == 0 else 0)
        self.reg.p = p | FU

    def _load(self, dst: Dst, value: int, mem_wr: bool) -> None:
        value &= 0xFF
        r, a = self.reg, self.addr
        if dst == Dst.NONE:
            if mem_wr:
                self.memory.write(self._mem_addr, self.last_bus)
            return
        if dst == Dst.A:
            r.a = value
        elif dst == Dst.X:
            r.x = value
        elif dst == Dst.Y:
            r.y = value
        elif dst == Dst.SP:
            r.sp = value
        elif dst == Dst.P:
            r.p = (value | FU) & ~FB
        elif dst == Dst.PCL:
            a.pcl = value
        elif dst == Dst.PCH:
            a.pch = value
        elif dst == Dst.MDR:
            a.mdr = value
        elif dst == Dst.T:
            r.t = value
        elif dst == Dst.MARL:
            a.marl = value
        elif dst == Dst.MARH:
            a.marh = value
        elif dst == Dst.ALU_A:
            self.alu.a = value
        elif dst == Dst.ALU_B:
            self.alu.b = value
        elif dst == Dst.IR:
            a.ir = value
        elif dst == Dst.MEM:
            self.memory.write(self._mem_addr, value)

    def _phi1(self, cw: CW) -> None:
        self._mem_addr = self.addr.address_bus(cw.addr_pc, cw.addr_sp, self.reg.sp)
        if cw.mem_rd:
            bus = self.memory.read(self._mem_addr)
        else:
            bus = self._drive(cw)
        self.last_bus = bus
        if cw.alu != AluOp.NOP:
            a = bus if cw.alu_a_bus else None
            b = (0xFF if self.addr.mdr & 0x80 else 0x00) if cw.alu_b_m7ext else None
            self.alu.evaluate(cw.alu, cw.cin, self.reg.p, cw.invert_b, a=a, b=b)
            self.last_bus = self.alu.result

    def _phi2(self, cw: CW) -> None:
        bus_in = self.last_bus
        if cw.alu != AluOp.NOP:
            bus = self.alu.result
            self.last_bus = bus
        else:
            bus = bus_in
        if cw.flags:
            if cw.alu != AluOp.NOP:
                self.reg.p = self.alu.apply_flags(self.reg.p, cw.flags)
            elif not (cw.reg_inc or cw.reg_dec):
                self._apply_nz(bus_in, cw.flags)
        inc = cw.reg_inc or cw.reg_dec
        inc_dst = cw.dst if cw.dst not in (Dst.NONE, Dst.MEM) else Dst.SP
        if cw.dst == Dst.MEM or cw.mem_wr:
            self._load(Dst.MEM, bus, True)
        elif cw.dst != Dst.NONE and not (inc and cw.dst == inc_dst):
            self._load(cw.dst, bus, False)
        if cw.also_alu_b:
            self.alu.b = bus_in & 0xFF
        if inc:
            delta = 1 if cw.reg_inc else -1
            val = (self._get8(inc_dst) + delta) & 0xFF
            self._load(inc_dst, val, False)
            if cw.flags and cw.alu == AluOp.NOP:
                self._apply_nz(val, cw.flags)
        if cw.pc_inc:
            # Dedicated incrementer; may share this Φ2 with a dest LOAD.
            self.addr.load_pc_plus1()

    def run(self, max_instructions: int | None = None) -> None:
        while not self.halted:
            self.step()
            if max_instructions is not None and self.instructions >= max_instructions:
                break
