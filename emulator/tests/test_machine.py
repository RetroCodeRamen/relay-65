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

    def test_program_goes_through_mar_not_pc_index(self):
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

    def test_fetch_reads_pc_even_if_mar_is_wrong(self):
        """ADDR_PC is a real 2:1; fetch must not depend on MAR being preloaded."""
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
        m.cpu.addr.marl = 0x00
        m.cpu.addr.marh = 0x00
        m.cpu.state = "FETCH"
        m.cpu.ustep = 0
        for _ in range(5000):
            m.step()
            if m.memory.read(0x0010) == 0x42:
                break
        self.assertEqual(m.memory.read(0x0010), 0x42)

    def test_design_b_fetch_is_one_packed_row(self):
        from relay65.isa import FETCH, fetch_byte, ld, pc_inc, st, transfer
        from relay65.signals import Dst, Src

        self.assertEqual(len(FETCH()), 1)
        self.assertEqual(len(fetch_byte()), 1)
        self.assertEqual(len(pc_inc()), 1)
        self.assertTrue(FETCH()[0].addr_pc)
        self.assertTrue(FETCH()[0].pc_inc)
        self.assertTrue(fetch_byte()[0].addr_pc and fetch_byte()[0].pc_inc)
        # LDA/STA abs: MAR loaded from the operand bytes, not via MDR+T copies.
        self.assertEqual(len(ld(Dst.A, "abs")), 3)
        self.assertEqual(len(st(Src.A, "abs")), 3)
        self.assertEqual(len(ld(Dst.A, "imm")), 1)
        self.assertEqual(len(transfer(Src.A, Dst.X)), 1)

    def test_helpers_are_one_row_where_relays_allow(self):
        from relay65.isa import branch, inc_reg, jsr, pha, pla, rts
        from relay65.signals import Cond, Dst, Src

        self.assertEqual(len(inc_reg(Src.Y, Dst.Y, 1)), 1)
        self.assertTrue(inc_reg(Src.Y, Dst.Y, 1)[0].reg_inc)
        self.assertEqual(len(pha()), 1)
        self.assertTrue(pha()[0].addr_sp and pha()[0].reg_dec)
        self.assertEqual(len(pla()), 2)
        self.assertEqual(len(branch(Cond.C)), 4)
        self.assertTrue(branch(Cond.C)[0].also_alu_b)
        self.assertEqual(len(jsr()), 5)
        self.assertEqual(len(rts()), 5)


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

    def test_lda_tax_sets_z_from_bus(self):
        m = self.run_until_loop(
            """
            .org $0200
            lda #$00
            tax
            done: jmp done
            """
        )
        self.assertEqual(m.cpu.a, 0)
        self.assertEqual(m.cpu.x, 0)
        self.assertTrue(m.cpu.p & 0x02)
        self.assertFalse(m.cpu.p & 0x80)

    def test_bit_takes_n_from_memory_not_and(self):
        m = self.run_until_loop(
            """
            .org $0200
            lda #$80
            sta $10
            lda #$01
            bit $10
            done: jmp done
            """
        )
        self.assertEqual(m.cpu.a, 0x01)
        self.assertTrue(m.cpu.p & 0x80)  # N from $80, not from $01 & $80
        self.assertTrue(m.cpu.p & 0x02)  # Z from A AND M == 0
        self.assertFalse(m.cpu.p & 0x40)

    def test_packed_lda_imm_microsteps(self):
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
        start = m.cpu.microcycles
        m.cpu.step_instruction()
        # FETCH 1 + execute 1 (MEM→A, NZ, PC+1, END)
        self.assertEqual(m.cpu.a, 0x42)
        self.assertEqual(m.cpu.microcycles - start, 2)

    def test_iny_wraps_and_bne_loop(self):
        m = self.run_until_loop(
            """
            .org $0200
            ldy #$fe
            iny
            iny
            sty $20
            ldx #$00
            loop:
            inx
            cpx #$03
            bne loop
            stx $21
            done: jmp done
            """
        )
        self.assertEqual(m.memory.read(0x0020), 0x00)
        self.assertEqual(m.memory.read(0x0021), 0x03)
        self.assertTrue(m.cpu.p & 0x02)

    def test_pha_writes_stack_page_not_mar(self):
        m = self.run_until_loop(
            """
            .org $0200
            ldx #$ff
            txs
            lda #$42
            pha
            lda #$00
            pla
            sta $20
            done: jmp done
            """
        )
        self.assertEqual(m.memory.read(0x0020), 0x42)
        self.assertEqual(m.memory.read(0x01FF), 0x42)

    def test_lda_abs_x_sta_zp(self):
        m = self.run_until_loop(
            """
            .org $0200
            lda #$99
            sta $12
            ldx #$02
            lda $10,x
            sta $20
            inc $20
            done: jmp done
            """
        )
        self.assertEqual(m.memory.read(0x0020), 0x9A)
        self.assertEqual(m.cpu.a, 0x99)


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

    def test_minute_speed_is_sixty_times_relay(self):
        from relay65.timing import MINUTE_FACTOR, WallClock

        clk = WallClock()
        clk.set_speed("minute")
        self.assertFalse(clk.overclock)
        self.assertAlmostEqual(clk.period_s, 0.020 / MINUTE_FACTOR)
        self.assertEqual(clk.label(), "1s=1min")
        self.assertEqual(clk.cycle_speed(), "warp")
        self.assertTrue(clk.overclock)
        self.assertEqual(clk.label(), "WARP")
        self.assertEqual(clk.cycle_speed(), "relay")
        self.assertEqual(clk.label(), "RELAY 20ms/µstep")
        clk.set_overclock(True)
        self.assertEqual(clk.speed, "warp")
        clk.set_overclock(False)
        self.assertEqual(clk.speed, "relay")

    def test_step_does_not_sleep(self):
        import time

        m = Machine()
        t0 = time.perf_counter()
        for _ in range(2000):
            m.step()
        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_real_time_tracks_microsteps_even_in_warp(self):
        from relay65.timing import WallClock, format_duration

        self.assertEqual(format_duration(0), "0.0s")
        self.assertEqual(format_duration(75), "1m 15s")
        self.assertEqual(format_duration(3661), "1h 01m 01s")
        self.assertEqual(format_duration(90000), "1d 01h 00m")

        clk = WallClock()
        clk.configure(overclock=True)
        clk.add_usteps(50)
        self.assertAlmostEqual(clk.real_run_s(), 1.0)
        clk.configure(overclock=True, datasheet=True)
        self.assertAlmostEqual(clk.real_run_s(), 0.5)
        fields = clk.runtime_fields()
        self.assertEqual(fields["real"], "0.5s")
        self.assertAlmostEqual(fields["real_ms"], 10.0)

    def test_host_timer_pauses_when_stopped(self):
        import time

        m = Machine()
        m.running = False
        m.clock.reset_runtime()
        m.running = True
        time.sleep(0.06)
        running = m.clock.host_run_s()
        m.running = False
        frozen = m.clock.host_run_s()
        time.sleep(0.06)
        self.assertGreater(running, 0.03)
        self.assertAlmostEqual(m.clock.host_run_s(), frozen, delta=0.02)

    def test_step_counts_real_time_when_stopped(self):
        m = Machine()
        m.running = False
        m.clock.reset_runtime()
        m.step()
        self.assertEqual(m.clock.real_run_s(), 0.0)
        m.step_instruction()
        self.assertGreater(m.clock.real_run_s(), 0.0)
        self.assertIn("HOST", m.clock.runtime_label())
        self.assertIn("REAL", m.clock.runtime_label())


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

    def test_reset_rewinds_and_keeps_run_stop(self):
        m = Machine()
        m.entry = 0x0200
        m.cpu.pc = 0x1234
        m.running = False
        m.restart_loaded()
        self.assertFalse(m.running)
        self.assertEqual(m.cpu.pc, 0x0200)
        m.cpu.pc = 0x1234
        m.running = True
        m.restart_loaded()
        self.assertTrue(m.running)
        self.assertEqual(m.cpu.pc, 0x0200)

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
        for _ in range(1_200_000):
            m.step()
            if b"_> " in bytes(m.uart.tx_log):
                break
        self.assertIn(b"Clack", bytes(m.uart.tx_log))
        self.assertIn(b"_> ", bytes(m.uart.tx_log))
        return m

    @staticmethod
    def _send_line(
        m: Machine,
        line: bytes,
        needle: bytes,
        limit: int = 1_500_000,
        wait_prompt: bool = False,
    ) -> bytes:
        start = len(m.uart.tx_log)
        m.uart.push_rx(line)
        for _ in range(limit):
            m.step()
            extra = bytes(m.uart.tx_log[start:])
            if needle not in extra or len(m.uart.rx) != 0:
                continue
            if wait_prompt and not extra.endswith(b"_> "):
                continue
            return extra
        return bytes(m.uart.tx_log[start:])

    def test_console_echoes_a_line(self):
        m = self._boot_console()
        tx = self._send_line(m, b"help\n", b"ls cd pwd", wait_prompt=True)
        self.assertIn(b"ls cd pwd", tx)
        self.assertIn(b"man NAME", tx)

    def test_console_peek_poke(self):
        m = self._boot_console()
        self._send_line(m, b"poke 7000 aa\n", b"wrote 1", wait_prompt=True)
        tx = self._send_line(m, b"peek 7000\n", b"7000: aa", wait_prompt=True)
        self.assertIn(b"7000: aa", tx)
        self.assertEqual(m.memory.read(0x7000), 0xAA)

    def test_console_tiny_basic(self):
        m = self._boot_console()
        self._send_line(m, b"basic\n", b"READY")
        tx = self._send_line(m, b"PRINT 1+2\n", b"3\n")
        self.assertIn(b"3\n", tx)
        self._send_line(m, b"10 PRINT 7\n", b"10 PRINT 7")
        tx = self._send_line(m, b"RUN\n", b"ok")
        self.assertIn(b"7", tx)
        self.assertIn(b"ok", tx)

    def test_console_ls_man_edit(self):
        m = self._boot_console()
        tx = self._send_line(m, b"ls\n", b"www", wait_prompt=True)
        self.assertIn(b"bin", tx)
        self.assertIn(b"etc", tx)
        tx = self._send_line(m, b"ls /bin\n", b"basic", wait_prompt=True)
        self.assertIn(b"basic", tx)
        self.assertIn(b"ed", tx)
        tx = self._send_line(m, b"man basic\n", b"BYE", wait_prompt=True)
        self.assertIn(b"PRINT", tx)
        self.assertIn(b"BYE", tx)
        self._send_line(m, b"edit\n", b"first line replaces")
        self._send_line(m, b"hello from ed\n", b"hello from ed")
        self._send_line(m, b".\n", b"saved", wait_prompt=True)
        tx = self._send_line(m, b"cat /tmp/notes\n", b"hello from ed", wait_prompt=True)
        self.assertIn(b"hello from ed", tx)


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
            addr_sp=True,
            reg_inc=True,
            reg_dec=False,
            alu_a_bus=True,
            alu_b_m7ext=True,
            also_alu_b=True,
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
