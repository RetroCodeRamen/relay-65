from __future__ import annotations

import unittest
from pathlib import Path

from relay65.assemble import assemble
from relay65.machine import Machine
from relay65.mmap import ROM_BASE
from relay65.signals import AluOp, Cin


ROOT = Path(__file__).resolve().parent.parent


class DatapathTests(unittest.TestCase):
    def test_alu_add_is_shared_unit(self):
        from relay65.alu import ALUCard

        alu = ALUCard()
        alu.a = 0x10
        alu.b = 0x01
        r = alu.evaluate(AluOp.ADD, Cin.ZERO, 0x20, False)
        self.assertEqual(r, 0x11)
        self.assertEqual(alu.c_latch, 0)

    def test_ea_memory_uses_mar(self):
        img = assemble(
            """
            .org $0200
            lda #$42
            sta $10
            done: jmp done
            """
        )
        m = Machine()
        m.load_image(img.origin, img.data)
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(5000):
            m.step()
            if m.memory.read(0x0010) == 0x42:
                break
        self.assertEqual(m.memory.read(0x0010), 0x42)
        self.assertEqual(m.cpu.a, 0x42)


    def test_fast_fetch_and_pc_inc_lengths(self):
        from relay65.isa import FETCH, fetch_byte, pc_inc

        self.assertEqual(len(FETCH()), 2)
        self.assertEqual(len(fetch_byte()), 2)
        self.assertEqual(len(pc_inc()), 1)
        self.assertTrue(FETCH()[0].addr_pc)
        self.assertTrue(pc_inc()[0].pc_inc)

    def test_lda_imm_is_eight_microsteps(self):
        img = assemble(
            """
            .org $0200
            lda #$42
            done: jmp done
            """
        )
        m = Machine()
        m.load_image(img.origin, img.data)
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        m.cpu.step_instruction()
        self.assertEqual(m.cpu.a, 0x42)
        self.assertEqual(m.cpu.microcycles, 8)
        self.assertEqual(m.cpu.pc, 0x0202)


class IsaTests(unittest.TestCase):
    def run_until_loop(self, src: str, addr: int = 0x0200, limit: int = 20000) -> Machine:
        img = assemble(src)
        m = Machine()
        m.load_image(img.origin, img.data)
        m.reset()
        m.cpu.pc = addr
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        seen = set()
        for _ in range(limit):
            key = (m.cpu.pc, m.cpu.state, m.cpu.ustep)
            m.step()
            if m.cpu.state == "FETCH" and m.cpu.ustep == 0:
                if m.cpu.pc in seen and m.cpu.addr.ir == 0x4C:
                    break
                seen.add(m.cpu.pc)
        return m

    def test_jsr_rts_and_stack(self):
        m = self.run_until_loop(
            """
            .org $0200
            ldx #$FF
            txs
            jsr sub
            lda #$99
            sta $20
            done: jmp done
            sub:
            lda #$55
            sta $21
            rts
            """
        )
        self.assertEqual(m.memory.read(0x0021), 0x55)
        self.assertEqual(m.memory.read(0x0020), 0x99)

    def test_hello_uart(self):
        img = assemble((ROOT / "programs" / "hello.s").read_text())
        m = Machine()
        m.load_image(img.origin, img.data)
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(50000):
            m.step()
            if bytes(m.uart.tx_log).endswith(b"Hello, Relay-65\n"):
                break
        self.assertEqual(bytes(m.uart.tx_log), b"Hello, Relay-65\n")


class MonitorTests(unittest.TestCase):
    def test_reset_vector_and_banner(self):
        img = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        m = Machine()
        m.load_image(img.origin, img.data)
        m.reset()
        for _ in range(200000):
            m.step()
            if b"Relay-65 monitor" in bytes(m.uart.tx_log) and b">" in bytes(m.uart.tx_log):
                break
        text = bytes(m.uart.tx_log).decode("ascii", errors="replace")
        self.assertIn("Relay-65 monitor v0.1", text)
        self.assertIn(">", text)


class LampTests(unittest.TestCase):
    def test_star_dot_bits(self):
        from relay65.leds import bits

        self.assertEqual(bits(0xA5, 8), "*.*..*.*")
        self.assertEqual(bits(0, 8), "........")
        self.assertEqual(bits(0xFF, 8), "********")
        self.assertEqual(bits(0xFF00, 16), "******** ........")

    def test_sample_follows_mar_and_bus(self):
        from relay65.leds import sample

        m = Machine()
        m.cpu.addr.marl = 0x00
        m.cpu.addr.marh = 0xC0
        m.cpu.last_bus = 0x5A
        m.cpu.addr.ir = 0xA9
        text = sample(m).text()
        self.assertIn("ADDR", text)
        self.assertIn("$C000", text)
        self.assertIn("$5A", text)
        self.assertIn("Φ", text)
    def test_c_printf_on_uart(self):
        path = ROOT.parent / "software" / "cc65" / "hello.bin"
        if not path.exists():
            self.skipTest("build software/cc65/hello.bin first")
        rom = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        m = Machine()
        m.load_image(rom.origin, rom.data)
        m.load_ram(0x0200, path.read_bytes())
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(2_000_000):
            m.step()
            if b"Relay-65 cc65 runtime" in bytes(m.uart.tx_log):
                break
        self.assertIn(b"Relay-65 cc65 runtime", bytes(m.uart.tx_log))
    def test_timer_irq_via_ram_vector(self):
        rom = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        img = assemble(
            """
            .org $0200
            ldx #$FF
            txs
            lda #<irqh
            sta $F0
            lda #>irqh
            sta $F1
            lda #1
            sta $C022
            cli
            wait:
            lda $40
            beq wait
            jmp wait
            irqh:
            inc $40
            lda #$80
            sta $C023
            rti
            """
        )
        m = Machine()
        m.load_image(rom.origin, rom.data)
        m.load_image(img.origin, img.data)
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(200000):
            m.step()
            if m.memory.read(0x0040) != 0:
                break
        self.assertNotEqual(m.memory.read(0x0040), 0)


class TimingTests(unittest.TestCase):
    def test_leeway_is_10ms_times_two_phases(self):
        from relay65.timing import microstep_period_s

        self.assertAlmostEqual(microstep_period_s(), 0.020)
        self.assertAlmostEqual(microstep_period_s(datasheet=True), 0.010)
        self.assertEqual(microstep_period_s(overclock=True), 0.0)
        self.assertAlmostEqual(microstep_period_s(phase_ms=10), 0.020)

    def test_step_does_not_sleep(self):
        import time

        m = Machine()
        t0 = time.perf_counter()
        for _ in range(2000):
            m.step()
        self.assertLess(time.perf_counter() - t0, 1.0)


class PanelOpsTests(unittest.TestCase):
    def test_examine_deposit_and_next(self):
        from relay65.panelops import deposit, deposit_next, examine, examine_next

        m = Machine()
        m.memory.write(0x0200, 0xAA)
        m.memory.write(0x0201, 0xBB)
        examine(m, 0x0200)
        self.assertEqual(m.cpu.pc, 0x0200)
        self.assertEqual(m.cpu.last_bus, 0xAA)
        self.assertEqual(examine_next(m, 0x0200), 0x0201)
        self.assertEqual(m.cpu.last_bus, 0xBB)
        deposit(m, 0x0200, 0x11)
        self.assertEqual(m.memory.read(0x0200), 0x11)
        self.assertEqual(deposit_next(m, 0x0200, 0x22), 0x0201)
        self.assertEqual(m.memory.read(0x0200), 0x22)
        self.assertEqual(m.cpu.pc, 0x0201)

    def test_uart_clear(self):
        m = Machine()
        m.uart.push_rx(b"hi")
        m.uart.tx_log.extend(b"out")
        m.uart.clear()
        self.assertEqual(len(m.uart.rx), 0)
        self.assertEqual(bytes(m.uart.tx_log), b"")


class ContikiTests(unittest.TestCase):
    def test_hello_world_on_uart(self):
        path = ROOT.parent / "software" / "contiki" / "hello-world.bin"
        if not path.exists():
            self.skipTest("make -C software/contiki hello")
        rom = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        m = Machine()
        m.load_image(rom.origin, rom.data)
        m.load_ram(0x0200, path.read_bytes())
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(500_000):
            m.step()
            tx = bytes(m.uart.tx_log)
            if b"Hello, world" in tx and b"Contiki on Relay-65" in tx:
                break
        tx = bytes(m.uart.tx_log)
        self.assertIn(b"Hello, world", tx)
        self.assertIn(b"Contiki on Relay-65", tx)

    def _boot_console(self) -> Machine:
        path = ROOT.parent / "software" / "contiki" / "console.bin"
        if not path.exists():
            self.skipTest("make -C software/contiki")
        rom = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        m = Machine()
        m.load_image(rom.origin, rom.data)
        m.load_ram(0x0200, path.read_bytes())
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(800_000):
            m.step()
            if b"console ready" in bytes(m.uart.tx_log):
                break
        self.assertIn(b"console ready", bytes(m.uart.tx_log))
        self.assertIn(b"RELAY65 BASIC", bytes(m.uart.tx_log))
        self.assertIn(b"BYTES RAM", bytes(m.uart.tx_log))
        self.assertIn(b"FREE", bytes(m.uart.tx_log))
        return m

    @staticmethod
    def _send_line(m: Machine, line: bytes, needle: bytes, limit: int = 1_500_000) -> bytes:
        m.uart.push_rx(line)
        for _ in range(limit):
            m.step()
            if needle in bytes(m.uart.tx_log):
                break
        return bytes(m.uart.tx_log)

    def test_console_echoes_a_line(self):
        m = self._boot_console()
        tx = self._send_line(m, b"help\n", b"peek ADDR")
        self.assertIn(b"peek ADDR", tx)

    def test_console_peek_poke(self):
        m = self._boot_console()
        self._send_line(m, b"poke 7000 aa\n", b"wrote 1")
        tx = self._send_line(m, b"peek 7000\n", b"7000: aa")
        self.assertIn(b"7000: aa", tx)
        self.assertEqual(m.memory.read(0x7000), 0xAA)

    def test_console_tiny_basic(self):
        m = self._boot_console()
        self._send_line(m, b"basic\n", b"READY")
        tx = self._send_line(m, b"PRINT 1+2\n", b"3")
        self.assertIn(b"3", tx)
        self._send_line(m, b"10 PRINT 7\n", b"10 PRINT 7")
        tx = self._send_line(m, b"RUN\n", b"ok")
        self.assertIn(b"7", tx)
        self.assertIn(b"ok", tx)


class ControlStoreTests(unittest.TestCase):
    def test_pack_roundtrip(self):
        from relay65.signals import AluOp, CW, Cin, Cond, Dst, Src

        cw = CW(
            src=Src.PCL,
            dst=Dst.ALU_A,
            alu=AluOp.ADC,
            cin=Cin.LATCH,
            flags=7,
            const=0x5A,
            mem_rd=True,
            mem_wr=False,
            end=True,
            end_if=Cond.NZ,
            p_or=0x30,
            invert_b=True,
            addr_pc=True,
            pc_inc=True,
        )
        self.assertEqual(CW.unpack(cw.pack()), cw)

    def test_execute_rom_fits_64_rows(self):
        from relay65.eeprom import ControlStore, USTEPS
        from relay65.isa import build_execute_rom

        for ir, prog in enumerate(build_execute_rom()):
            if prog is not None:
                self.assertLessEqual(len(prog), USTEPS, f"${ir:02X}")
        store = ControlStore.from_isa()
        self.assertEqual(len(store.execute), 256 * 64 * 8)

    def test_illegal_opcode_jams(self):
        m = Machine()
        m.memory.write(0x0200, 0x02, force_ram=True)
        m.reset()
        m.cpu.pc = 0x0200
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(200):
            m.step()
            if m.cpu.halted:
                break
        self.assertTrue(m.cpu.halted)

    def test_oe_released_after_microstep(self):
        from relay65.signals import Src

        m = Machine()
        m.reset()
        m.step()
        self.assertEqual(m.cpu.oe_src, Src.NONE)
        self.assertEqual(m.cpu.phi, 2)

    def test_timer_counts_phi2_not_instructions(self):
        m = Machine()
        m.reset()
        for _ in range(512):
            m.step()
        self.assertEqual(m.memory.timer.ticks, m.cpu.microcycles // 256)
        self.assertGreater(m.cpu.microcycles, m.cpu.instructions)


class FuzixMapTests(unittest.TestCase):
    def test_page_registers_map_512k(self):
        m = Machine()
        m.memory.write(0xC01A, 7)
        m.memory.write(0x8000, 0xA5, force_ram=True)
        self.assertEqual(m.memory.sram[7 * 0x4000], 0xA5)
        m.memory.write(0xC010, 0)
        self.assertEqual(m.memory.pages[2], 2)

    def test_rom_overlay_off_reads_ram(self):
        m = Machine()
        m.memory.rom[0] = 0x11
        m.memory.write(0xE000, 0x22, force_ram=True)
        self.assertEqual(m.memory.read(0xE000), 0x11)
        m.memory.write(0xC016, 0)
        self.assertEqual(m.memory.read(0xE000), 0x22)

    def test_cpu_write_through_under_rom(self):
        m = Machine()
        m.memory.rom[0] = 0x11
        m.memory.write(0xE000, 0x22)
        self.assertEqual(m.memory.read(0xE000), 0x11)
        self.assertEqual(m.memory.sram[0xE000], 0x22)
        m.memory.write(0xC016, 0)
        self.assertEqual(m.memory.read(0xE000), 0x22)

    def test_cf_identify_lba(self):
        m = Machine()
        m.memory.ide.load_image(bytes(1024))
        m.memory.write(0xC106, 0xE0)
        m.memory.write(0xC103, 0xAA)
        self.assertEqual(m.memory.read(0xC103), 0xAA)
        m.memory.write(0xC107, 0xEC)
        self.assertEqual(m.memory.read(0xC107) & 0x80, 0x80)
        self.assertEqual(m.memory.read(0xC107) & 0x08, 0x08)
        ident = bytes(m.memory.read(0xC100) for _ in range(512))
        self.assertEqual(ident[99] & 0x02, 0x02)
        self.assertEqual(ident[120], 2)

    def test_esp32_mailbox_http(self):
        m = Machine()
        self.assertEqual(m.memory.read(0xC200), 0x45)
        self.assertEqual(m.memory.read(0xC201), 0x32)
        self.assertEqual(m.memory.read(0xC202) & 0x04, 0x04)
        path = b"GET / HTTP/1.0\r\n\r\n"
        m.memory.write(0xC205, len(path))
        m.memory.write(0xC206, 0)
        m.memory.write(0xC203, 0x01)
        for b in path:
            m.memory.write(0xC204, b)
        m.memory.write(0xC203, 0x02)
        n = m.memory.read(0xC205) | (m.memory.read(0xC206) << 8)
        body = bytes(m.memory.read(0xC204) for _ in range(n))
        self.assertIn(b"Relay-65 click-click", body)
        self.assertTrue(m.memory.esp32.tx_log)


class FuzixBootTests(unittest.TestCase):
    def _with_monitor(self, m: Machine) -> None:
        rom = assemble((ROOT / "rom" / "monitor.s").read_text(), default_origin=ROM_BASE)
        m.load_image(rom.origin, rom.data)

    def test_jumper_loads_stub_from_cf(self):
        stub = assemble(
            """
            .org $4002
            ldx #0
        s:
            lda msg,x
            beq hang
            jsr tx
            inx
            jmp s
        hang:
            jmp hang
        tx:
            pha
        tw:
            lda $C001
            and #2
            beq tw
            pla
            sta $C000
            rts
        msg:
            .byte "cfboot", $00
            """
        )
        kernel = bytearray(65536)
        kernel[stub.origin : stub.origin + len(stub.data)] = stub.data
        m = Machine()
        self._with_monitor(m)
        m.load_fuzix(bytes(kernel))
        self.assertTrue(m.memory.rom_enable)
        self.assertIsNone(m.entry)
        m.reset()
        for i in range(80_000_000):
            m.step()
            if (i & 0xFFFF) == 0 and b"cfboot" in bytes(m.uart.tx_log):
                break
        self.assertIn(b"cfboot", bytes(m.uart.tx_log))
        self.assertFalse(m.memory.rom_enable)
        self.assertFalse(m.cpu.halted)

    def test_kernel_signs_on(self):
        path = ROOT.parent / "fuzix" / "Kernel" / "fuzix.bin"
        if not path.exists():
            self.skipTest("make -C software/fuzix")
        m = Machine()
        self._with_monitor(m)
        m.load_fuzix(path.read_bytes())
        m.reset()
        for i in range(80_000_000):
            m.step()
            if m.cpu.halted:
                break
            if (i & 0xFFFF) == 0 and b"FUZIX version" in bytes(m.uart.tx_log):
                break
        tx = bytes(m.uart.tx_log)
        self.assertIn(b"FUZIX version", tx)
        self.assertFalse(m.cpu.halted)


if __name__ == "__main__":
    unittest.main()
