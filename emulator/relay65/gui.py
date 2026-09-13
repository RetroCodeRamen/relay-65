"""Graphical front panel + serial terminal (tkinter, no extra packages).

Same layout as webui.py: serial, CLOCK / MEMORY, HOST/REAL/WARP, MACHINE | 6502.
Chrome is the Aero graphite look, within what tkinter can draw.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont

from .leds import sample
from .panelops import deposit, deposit_next, examine, examine_next

BG = "#0c1016"
METAL = "#1a1618"
METAL_CPU = "#162230"
GLASS = "#1c2838"
LED_ON = "#ff2a28"
LED_OFF = "#280808"
TEXT = "#eef4fa"
DIM = "#8aa0b8"
CYAN = "#5ec8e8"
SW_ON = "#c8dce8"
SW_OFF = "#1a2430"
BTN = "#2c4058"
BTN_HI = "#3a5878"
ACCENT = "#8ab0c8"
ORANGE = "#f0a050"
MACHINE_TITLE = "#ecd8c8"
CPU_TITLE = "#d0eefc"
EDGE = "#5a7088"

P_BITS = ("N", "V", "U", "B", "D", "I", "Z", "C")
UI = "Segoe UI" if sys.platform == "win32" else "Helvetica"
MONO = "Consolas" if sys.platform == "win32" else "Courier"


class LampRow:
    def __init__(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        n: int,
        r: int = 11,
        gap: int = 22,
        group: int = 8,
        labels: bool = False,
        names: tuple[str, ...] | None = None,
    ):
        self.canvas = canvas
        self.ids = []
        cx = x
        for i in range(n):
            bit = n - 1 - i
            caption = names[i] if names else (str(bit) if labels else None)
            if caption is not None:
                canvas.create_text(cx, y - 19, text=caption, fill=DIM, font=(MONO, 11))
            oid = canvas.create_oval(cx - r, y - r, cx + r, y + r, fill=LED_OFF, outline="#1a0404")
            self.ids.append(oid)
            cx += gap
            if (i + 1) % group == 0 and i + 1 < n:
                cx += 11

    def set(self, value: int) -> None:
        n = len(self.ids)
        for i, oid in enumerate(self.ids):
            bit = n - 1 - i
            on = bool(value & (1 << bit))
            self.canvas.itemconfig(
                oid,
                fill=LED_ON if on else LED_OFF,
                outline="#ff6a60" if on else "#1a0404",
            )


class SwitchRow:
    def __init__(self, canvas: tk.Canvas, x: int, y: int, n: int, on_change, gap: int = 22, group: int = 8):
        self.canvas = canvas
        self.n = n
        self.value = 0
        self.on_change = on_change
        self.ids = []
        cx = x
        for i in range(n):
            bit = n - 1 - i
            rid = canvas.create_rectangle(
                cx - 9, y - 16, cx + 9, y + 16, fill=SW_OFF, outline="#0a0d12", tags=("sw", f"sw{bit}")
            )
            canvas.tag_bind(rid, "<Button-1>", lambda e, b=bit: self.toggle(b))
            self.ids.append((bit, rid))
            cx += gap
            if (i + 1) % group == 0 and i + 1 < n:
                cx += 11
        self.redraw()

    def toggle(self, bit: int) -> None:
        self.value ^= 1 << bit
        self.redraw()
        self.on_change()

    def set(self, value: int) -> None:
        self.value = value & ((1 << self.n) - 1)
        self.redraw()

    def redraw(self) -> None:
        for bit, rid in self.ids:
            on = bool(self.value & (1 << bit))
            self.canvas.itemconfig(
                rid,
                fill=SW_ON if on else SW_OFF,
                outline="#7aa0b8" if on else "#0a0d12",
            )


def _canvas_width(n: int, gap: int = 22, group: int = 8) -> int:
    extra = 11 * ((n - 1) // group)
    return 20 + n * gap + extra


class RelayGui:
    def __init__(self, machine, burst: int = 800, start_running: bool = False) -> None:
        self.machine = machine
        self.burst = burst
        machine.clock.reset_runtime()
        machine.running = start_running
        machine.clock.sync()
        self.root = tk.Tk()
        self.root.title("Relay-65")
        self.root.configure(bg=BG)
        self.root.minsize(1100, 640)
        self.root.geometry("1280x720")

        self._build_header()
        self._build_terminal()
        self._build_controls()
        self._build_panels()
        self._wire_uart()
        self._tick()

    def _section(self, parent, title: str, subtitle: str, metal: str, title_fg: str) -> tk.Frame:
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill=tk.X)
        tk.Label(head, text=title, fg=title_fg, bg=BG, font=(UI, 13, "bold")).pack(side=tk.LEFT)
        tk.Label(head, text="  " + subtitle, fg=DIM, bg=BG, font=(UI, 10)).pack(side=tk.LEFT)
        body = tk.Frame(wrap, bg=metal, padx=8, pady=8, highlightbackground=EDGE, highlightthickness=1)
        body.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        return body

    def _named_row(self, parent, title: str, *, side: str = "top", shift: int = 0) -> tk.Frame:
        bg = parent.cget("bg")
        row = tk.Frame(parent, bg=bg)
        if side == "left":
            row.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=0, padx=(shift, 6))
        else:
            row.pack(fill=tk.X, pady=0, padx=(-35 + shift, 0))
        tk.Label(row, text=title, fg=DIM, bg=bg, font=(MONO, 12), width=11, anchor="e").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        return row

    def _lamps(
        self,
        parent,
        title: str,
        n: int,
        *,
        labels: bool = False,
        names: tuple[str, ...] | None = None,
        hex_digits: int = 2,
        side: str = "top",
        shift: int = 0,
    ) -> tuple[LampRow, tk.StringVar]:
        row = self._named_row(parent, title, side=side, shift=shift)
        bg = parent.cget("bg")
        h = 53 if labels or names else 34
        canvas = tk.Canvas(row, width=_canvas_width(n), height=h, bg=bg, highlightthickness=0)
        canvas.pack(side=tk.LEFT)
        y = 32 if labels or names else 18
        lamps = LampRow(canvas, 8, y, n, labels=labels, names=names)
        hexv = tk.StringVar(value="$" + ("0" * hex_digits))
        tk.Label(row, textvariable=hexv, fg=TEXT, bg=bg, font=(MONO, 14), width=hex_digits + 1, anchor="w").pack(
            side=tk.LEFT, padx=8
        )
        return lamps, hexv

    def _switches(self, parent, title: str, n: int, on_change, *, side: str = "top", shift: int = 0) -> SwitchRow:
        row = self._named_row(parent, title, side=side, shift=shift)
        bg = parent.cget("bg")
        canvas = tk.Canvas(row, width=_canvas_width(n), height=42, bg=bg, highlightthickness=0)
        canvas.pack(side=tk.LEFT)
        return SwitchRow(canvas, 8, 22, n, on_change)

    def _pair(self, parent, shift: int = 0) -> tk.Frame:
        f = tk.Frame(parent, bg=parent.cget("bg"))
        f.pack(fill=tk.X, padx=(-35 + shift, 0))
        return f

    def _build_header(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill=tk.X, padx=12, pady=(6, 0))
        mark = tk.Canvas(frame, width=8, height=26, bg=BG, highlightthickness=0)
        mark.pack(side=tk.LEFT, padx=(0, 10))
        mark.create_rectangle(0, 0, 8, 26, fill=CYAN, outline="")
        tk.Label(frame, text="RELAY-65", fg="#f6fbff", bg=BG, font=(UI, 14, "bold")).pack(side=tk.LEFT)
        tk.Label(
            frame,
            text="  UART $C000 · MACHINE = relay bus/sequencer · 6502 = A X Y SP P PC · STEP ROW = EEPROM word · STEP OP = instruction",
            fg=DIM,
            bg=BG,
            font=(UI, 9),
        ).pack(side=tk.LEFT)

    def _build_terminal(self) -> None:
        wrap = tk.Frame(self.root, bg=GLASS, padx=8, pady=6, highlightbackground=EDGE, highlightthickness=1)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 0))
        tk.Label(
            wrap,
            text="SERIAL · UART $C000 · RETURN = CR · BACKSPACE = $08 · DELETE = $7F",
            fg="#3a88a8",
            bg=GLASS,
            font=(MONO, 8),
        ).pack(anchor="w")
        self.term_font = tkfont.Font(family=MONO, size=21)
        self.term = tk.Text(
            wrap,
            bg="#070b10",
            fg="#c6e8c0",
            insertbackground="#5ec8e8",
            font=self.term_font,
            wrap=tk.CHAR,
            height=10,
            undo=False,
            highlightbackground="#0a1218",
            highlightthickness=1,
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )
        self.term.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.term.bind("<Key>", self._on_key)
        self.term.bind("<Button-1>", lambda e: self.term.focus_set())
        self.term.focus_set()

    def _build_panels(self) -> None:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 8))
        left = tk.Frame(row, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right = tk.Frame(row, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self._build_machine_panel(left)
        self._build_cpu_panel(right)

    def _build_machine_panel(self, parent) -> None:
        body = self._section(parent, "MACHINE", "MAR / bus / IR / sequencer", metal=METAL, title_fg=MACHINE_TITLE)
        self.addr_lamps, self.addr_hex_var = self._lamps(body, "MAR", 16, labels=True, hex_digits=4)
        self.addr_sw = self._switches(body, "ADDR SW", 16, self._sw_changed)
        pair = self._pair(body)
        self.data_lamps, self.data_hex_var = self._lamps(pair, "BUS", 8, labels=True, hex_digits=2, side="left")
        self.ir_lamps, self.ir_hex_var = self._lamps(pair, "IR", 8, labels=True, hex_digits=2, side="left", shift=-40)
        pair2 = self._pair(body)
        self.data_sw = self._switches(pair2, "DATA SW", 8, self._sw_changed, side="left")
        seq = self._named_row(pair2, "SEQ", side="left", shift=-40)
        bg = body.cget("bg")
        self.stat_ids: dict[str, tuple[tk.Canvas, int]] = {}
        for name in ("RUN", "WAIT", "IRQ"):
            col = tk.Frame(seq, bg=bg)
            col.pack(side=tk.LEFT, padx=4)
            tk.Label(col, text=name, fg=DIM, bg=bg, font=(MONO, 11)).pack()
            c = tk.Canvas(col, width=27, height=27, bg=bg, highlightthickness=0)
            c.pack()
            oid = c.create_oval(2, 2, 25, 25, fill=LED_OFF, outline="#1a0404")
            self.stat_ids[name] = (c, oid)

    def _build_cpu_panel(self, parent) -> None:
        body = self._section(parent, "6502", "P = N V U B D I Z C", metal=METAL_CPU, title_fg=CPU_TITLE)
        self.pc_lamps, self.pc_hex_var = self._lamps(body, "PC", 16, labels=True, hex_digits=4, shift=-25)
        pair = self._pair(body, shift=-25)
        self.a_lamps, self.a_hex_var = self._lamps(pair, "A", 8, labels=True, side="left")
        self.x_lamps, self.x_hex_var = self._lamps(pair, "X", 8, labels=True, side="left", shift=-30)
        pair2 = self._pair(body, shift=-25)
        self.y_lamps, self.y_hex_var = self._lamps(pair2, "Y", 8, labels=True, side="left")
        self.sp_lamps, self.sp_hex_var = self._lamps(pair2, "SP", 8, labels=True, side="left", shift=-30)
        self.p_lamps, self.p_hex_var = self._lamps(body, "P", 8, names=P_BITS, shift=-25)

    def _btn(self, parent, label, cmd) -> tk.Button:
        b = tk.Button(
            parent,
            text=label,
            command=cmd,
            bg=BTN,
            fg="#f8fbff",
            activebackground=BTN_HI,
            activeforeground="#f8fbff",
            highlightbackground=ACCENT,
            highlightthickness=1,
            bd=1,
            relief=tk.RAISED,
            font=(UI, 10, "bold"),
            padx=10,
            pady=4,
        )
        b.pack(side=tk.LEFT, padx=3, fill=tk.X, expand=True)
        return b

    def _hex_entry(self, parent, width: int, value: str) -> tk.Entry:
        e = tk.Entry(
            parent,
            width=width,
            font=(MONO, 11),
            bg="#0e141c",
            fg=TEXT,
            insertbackground=CYAN,
            relief=tk.FLAT,
            highlightbackground="#3a5068",
            highlightthickness=1,
            highlightcolor=CYAN,
        )
        e.insert(0, value)
        e.pack(side=tk.LEFT, padx=(0, 4))
        e.bind("<Return>", lambda ev: self._apply_hex())
        return e

    def _build_controls(self) -> None:
        dock = tk.Frame(self.root, bg=BG)
        dock.pack(fill=tk.X, padx=12, pady=(6, 0))

        clock = tk.Frame(dock, bg=GLASS, padx=10, pady=6, highlightbackground=EDGE, highlightthickness=1)
        clock.pack(fill=tk.X)
        tk.Label(clock, text="CLOCK", fg=ORANGE, bg=GLASS, font=(UI, 8), width=8, anchor="w").pack(anchor="w")
        btns = tk.Frame(clock, bg=GLASS)
        btns.pack(fill=tk.X, pady=(2, 0))
        self._btn(btns, "RUN", self._run)
        self._btn(btns, "STOP", self._stop)
        self._btn(btns, "STEP ROW", self._step_row)
        self._btn(btns, "STEP OP", self._step_op)
        self._btn(btns, "RESET", self._reset)
        self.speed_btn = self._btn(btns, "SPEED", self._cycle_speed)

        mem = tk.Frame(dock, bg=GLASS, padx=10, pady=6, highlightbackground=EDGE, highlightthickness=1)
        mem.pack(fill=tk.X, pady=(5, 0))
        tk.Label(mem, text="MEMORY", fg=ORANGE, bg=GLASS, font=(UI, 8), width=8, anchor="w").pack(anchor="w")
        row = tk.Frame(mem, bg=GLASS)
        row.pack(fill=tk.X, pady=(2, 0))
        tk.Label(row, text="ADDR $", fg=DIM, bg=GLASS, font=(MONO, 10)).pack(side=tk.LEFT)
        self.addr_hex = self._hex_entry(row, 4, "0000")
        tk.Label(row, text=" DATA $", fg=DIM, bg=GLASS, font=(MONO, 10)).pack(side=tk.LEFT)
        self.data_hex = self._hex_entry(row, 2, "00")
        self._btn(row, "SET SW", self._apply_hex)
        self._btn(row, "EXAMINE", self._examine)
        self._btn(row, "EX NEXT", self._examine_next)
        self._btn(row, "DEPOSIT", self._deposit)
        self._btn(row, "DEP NEXT", self._deposit_next)
        self._btn(row, "CLR TTY", self._clear_tty)

        status = tk.Frame(dock, bg=BG)
        status.pack(fill=tk.X, pady=(6, 0))
        self.phase_var = tk.StringVar(value="RESET Φ0  u=0")
        tk.Label(
            status,
            textvariable=self.phase_var,
            fg=CYAN,
            bg="#080c12",
            font=(MONO, 11),
            anchor="w",
            padx=10,
            pady=4,
            highlightbackground="#2a4050",
            highlightthickness=1,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        for lab in ("WARP", "REAL", "HOST"):
            col = tk.Frame(status, bg=BG)
            col.pack(side=tk.RIGHT, padx=(16, 0))
            tk.Label(col, text=lab, fg=DIM, bg=BG, font=(UI, 8)).pack(anchor="w")
            var = tk.StringVar(value="—" if lab == "WARP" else "0.0s")
            tk.Label(col, textvariable=var, fg=TEXT, bg=BG, font=(MONO, 14)).pack(anchor="w")
            if lab == "HOST":
                self.host_var = var
            elif lab == "REAL":
                self.real_var = var
            else:
                self.warp_var = var

        self.clock_note = tk.StringVar(
            value="HOST is wall time while RUN is on. REAL is those same microsteps at the relay clock."
        )
        tk.Label(dock, textvariable=self.clock_note, fg=DIM, bg=BG, font=(UI, 9), anchor="w").pack(
            fill=tk.X, pady=(4, 0)
        )

    def _wire_uart(self) -> None:
        def tx(ch: int) -> None:
            ch &= 0xFF
            if ch in (8, 127):
                self.term.delete("end-2c")
            elif ch in (10, 13):
                self.term.insert("end-1c", "\n")
            elif 32 <= ch < 127:
                self.term.insert("end-1c", chr(ch))
            self.term.see(tk.END)

        self.machine.uart.on_tx = tx

    def _on_key(self, event: tk.Event) -> str:
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return "break"
        if event.keysym == "Return":
            self.machine.uart.push_rx(b"\r")
            return "break"
        if event.keysym == "BackSpace":
            self.machine.uart.push_rx(b"\x08")
            return "break"
        if event.keysym == "Delete":
            self.machine.uart.push_rx(b"\x7f")
            return "break"
        if event.char:
            self.machine.uart.push_rx(event.char.encode("ascii", errors="ignore"))
        return "break"

    def _run(self) -> None:
        self.machine.running = True
        self.machine.clock.sync()

    def _stop(self) -> None:
        self.machine.running = False

    def _cycle_speed(self) -> None:
        self.machine.clock.cycle_speed()
        self._refresh_lamps()

    def _step_row(self) -> None:
        self.machine.running = False
        self.machine.step_micro()
        self._refresh_lamps()

    def _step_op(self) -> None:
        self.machine.running = False
        self.machine.step_instruction()
        self._refresh_lamps()

    def _sw_changed(self) -> None:
        if not hasattr(self, "addr_hex"):
            return
        self.addr_hex.delete(0, tk.END)
        self.addr_hex.insert(0, f"{self.addr_sw.value:04X}")
        self.data_hex.delete(0, tk.END)
        self.data_hex.insert(0, f"{self.data_sw.value:02X}")

    def _apply_hex(self) -> None:
        try:
            self.addr_sw.set(int(self.addr_hex.get().strip() or "0", 16) & 0xFFFF)
            self.data_sw.set(int(self.data_hex.get().strip() or "0", 16) & 0xFF)
        except ValueError:
            return
        self._sw_changed()

    def _clear_tty(self) -> None:
        self.machine.uart.clear()
        self.term.delete("1.0", tk.END)

    def _reset(self) -> None:
        self.machine.restart_loaded()
        self._refresh_lamps()

    def _examine(self) -> None:
        self._apply_hex()
        examine(self.machine, self.addr_sw.value)
        self._refresh_lamps()

    def _examine_next(self) -> None:
        self.addr_sw.set(examine_next(self.machine, self.addr_sw.value))
        self._sw_changed()
        self._refresh_lamps()

    def _deposit(self) -> None:
        self._apply_hex()
        deposit(self.machine, self.addr_sw.value, self.data_sw.value)
        self._refresh_lamps()

    def _deposit_next(self) -> None:
        self._apply_hex()
        nxt = deposit_next(self.machine, self.addr_sw.value, self.data_sw.value)
        self.addr_sw.set(nxt)
        self._sw_changed()
        self._refresh_lamps()

    def _set_stat(self, name: str, on: bool) -> None:
        canvas, oid = self.stat_ids[name]
        canvas.itemconfig(
            oid,
            fill=LED_ON if on else LED_OFF,
            outline="#ff6a60" if on else "#1a0404",
        )

    def _refresh_lamps(self) -> None:
        s = sample(self.machine)
        self.addr_lamps.set(s.addr)
        self.data_lamps.set(s.data)
        self.ir_lamps.set(s.ir)
        self.pc_lamps.set(s.pc)
        self.a_lamps.set(s.a)
        self.x_lamps.set(s.x)
        self.y_lamps.set(s.y)
        self.sp_lamps.set(s.sp)
        self.p_lamps.set(s.p)
        self.addr_hex_var.set(f"${s.addr:04X}")
        self.data_hex_var.set(f"${s.data:02X}")
        self.ir_hex_var.set(f"${s.ir:02X}")
        self.pc_hex_var.set(f"${s.pc:04X}")
        self.a_hex_var.set(f"${s.a:02X}")
        self.x_hex_var.set(f"${s.x:02X}")
        self.y_hex_var.set(f"${s.y:02X}")
        self.sp_hex_var.set(f"${s.sp:02X}")
        self.p_hex_var.set(f"${s.p:02X}")
        self._set_stat("RUN", s.running and not s.wait)
        self._set_stat("WAIT", s.wait or not s.running)
        self._set_stat("IRQ", s.irq)
        halted = "HALTED" if self.machine.cpu.halted else ("RUN" if s.running and not s.wait else "STOP")
        self.phase_var.set(f"{s.phase}  u={s.ustep}  {halted}  {self.machine.clock.label()}")
        rt = self.machine.clock.runtime_fields()
        self.host_var.set(rt["host"])
        self.real_var.set(rt["real"])
        self.warp_var.set(rt["warp"])
        self.clock_note.set(
            f"HOST is wall time while RUN is on. REAL is those same microsteps "
            f"at {rt['real_ms']:.0f} ms each — how long the relays would need in real mode."
        )
        if hasattr(self, "speed_btn"):
            self.speed_btn.config(text=self.machine.clock.label())

    def _tick(self) -> None:
        if self.machine.running:
            clk = self.machine.clock
            if clk.overclock:
                for _ in range(self.burst):
                    self.machine.step()
                    if not self.machine.running:
                        break
            else:
                for _ in range(clk.due_steps()):
                    self.machine.step()
                    clk.account(1)
                    if not self.machine.running:
                        break
        self._refresh_lamps()
        self.root.after(16, self._tick)

    def run(self) -> None:
        self.root.mainloop()


def run_gui(machine, burst: int = 800, start_running: bool = False) -> int:
    RelayGui(machine, burst=burst, start_running=start_running).run()
    return 0
