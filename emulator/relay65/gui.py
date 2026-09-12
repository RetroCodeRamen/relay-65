"""Graphical front panel + serial terminal (tkinter, no extra packages).

Lamps and paddle switches are the Altair-style face. The text box is the
UART, the same serial connector the real machine will have.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .leds import sample
from .panelops import deposit, deposit_next, examine, examine_next


BG = "#1c1c1a"
METAL = "#2c2c28"
LED_ON = "#ff3030"
LED_OFF = "#4a1212"
TEXT = "#e8e0d0"
DIM = "#8a8070"
SW_ON = "#ddd5c8"
SW_OFF = "#3a3a36"


class LampRow:
    def __init__(self, canvas: tk.Canvas, x: int, y: int, n: int, r: int = 7, gap: int = 18, group: int = 8, labels: bool = False):
        self.canvas = canvas
        self.ids = []
        cx = x
        for i in range(n):
            bit = n - 1 - i
            if labels:
                canvas.create_text(cx, y - 14, text=str(bit), fill=DIM, font=("Courier", 8))
            oid = canvas.create_oval(cx - r, y - r, cx + r, y + r, fill=LED_OFF, outline="#111")
            self.ids.append(oid)
            cx += gap
            if (i + 1) % group == 0 and i + 1 < n:
                cx += 8

    def set(self, value: int) -> None:
        n = len(self.ids)
        for i, oid in enumerate(self.ids):
            bit = n - 1 - i
            self.canvas.itemconfig(oid, fill=LED_ON if value & (1 << bit) else LED_OFF)


class SwitchRow:
    def __init__(self, canvas: tk.Canvas, x: int, y: int, n: int, on_change, gap: int = 18, group: int = 8):
        self.canvas = canvas
        self.n = n
        self.value = 0
        self.on_change = on_change
        self.ids = []
        cx = x
        for i in range(n):
            bit = n - 1 - i
            rid = canvas.create_rectangle(cx - 6, y - 12, cx + 6, y + 12, fill=SW_OFF, outline="#111", tags=("sw", f"sw{bit}"))
            canvas.tag_bind(rid, "<Button-1>", lambda e, b=bit: self.toggle(b))
            self.ids.append((bit, rid))
            cx += gap
            if (i + 1) % group == 0 and i + 1 < n:
                cx += 8
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
            # paddle up = 1
            self.canvas.itemconfig(rid, fill=SW_ON if on else SW_OFF)


class RelayGui:
    def __init__(self, machine, burst: int = 800, start_running: bool = False) -> None:
        self.machine = machine
        self.burst = burst
        machine.running = start_running
        machine.clock.sync()
        self.root = tk.Tk()
        self.root.title("Relay-65")
        self.root.configure(bg=BG)
        self.root.minsize(720, 620)

        self._build_header()
        self._build_terminal()
        self._build_panel()
        self._wire_uart()
        self._tick()

    def _build_header(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill=tk.X, padx=12, pady=(8, 0))
        tk.Label(frame, text="RELAY-65", fg=TEXT, bg=BG, font=("Helvetica", 16, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="Serial on top (the console). Front panel below (lamps and paddles).",
            fg=DIM,
            bg=BG,
        ).pack(anchor="w")

    def _build_panel(self) -> None:
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill=tk.X, padx=12, pady=8)

        self.canvas = tk.Canvas(frame, width=700, height=248, bg=METAL, highlightthickness=0)
        self.canvas.pack(pady=8)

        self.canvas.create_text(12, 20, text="ADDR", fill=DIM, anchor="w", font=("Courier", 10))
        self.addr_lamps = LampRow(self.canvas, 70, 20, 16, labels=True)
        self.canvas.create_text(12, 62, text="A SW", fill=DIM, anchor="w", font=("Courier", 10))
        self.addr_sw = SwitchRow(self.canvas, 70, 62, 16, self._sw_changed)

        self.canvas.create_text(12, 108, text="DATA", fill=DIM, anchor="w", font=("Courier", 10))
        self.data_lamps = LampRow(self.canvas, 70, 108, 8, labels=True)
        self.canvas.create_text(250, 108, text="IR", fill=DIM, anchor="w", font=("Courier", 10))
        self.ir_lamps = LampRow(self.canvas, 280, 108, 8)

        self.canvas.create_text(12, 148, text="D SW", fill=DIM, anchor="w", font=("Courier", 10))
        self.data_sw = SwitchRow(self.canvas, 70, 148, 8, self._sw_changed)

        self.stat_ids = {}
        x = 70
        for name in ("RUN", "WAIT", "I", "IRQ", "N", "Z", "C", "V"):
            self.canvas.create_text(x, 198, text=name, fill=DIM, anchor="s", font=("Courier", 8))
            oid = self.canvas.create_oval(x - 6, 206, x + 6, 218, fill=LED_OFF, outline="#111")
            self.stat_ids[name] = oid
            x += 42

        hexrow = tk.Frame(frame, bg=BG)
        hexrow.pack(anchor="w", pady=4)
        tk.Label(hexrow, text="ADDR $", fg=DIM, bg=BG, font=("Courier", 11)).pack(side=tk.LEFT)
        self.addr_hex = tk.Entry(hexrow, width=4, font=("Courier", 12), bg="#2a2a26", fg=TEXT, insertbackground=TEXT)
        self.addr_hex.insert(0, "0000")
        self.addr_hex.pack(side=tk.LEFT)
        self.addr_hex.bind("<Return>", lambda e: self._apply_hex())
        tk.Label(hexrow, text="   DATA $", fg=DIM, bg=BG, font=("Courier", 11)).pack(side=tk.LEFT)
        self.data_hex = tk.Entry(hexrow, width=2, font=("Courier", 12), bg="#2a2a26", fg=TEXT, insertbackground=TEXT)
        self.data_hex.insert(0, "00")
        self.data_hex.pack(side=tk.LEFT)
        self.data_hex.bind("<Return>", lambda e: self._apply_hex())
        tk.Button(hexrow, text="SET SWITCHES", command=self._apply_hex, bg="#4a4840", fg=TEXT).pack(side=tk.LEFT, padx=8)

        self.hex_var = tk.StringVar(value="")
        tk.Label(frame, textvariable=self.hex_var, fg=TEXT, bg=BG, font=("Courier", 12)).pack(anchor="w")

        btns = tk.Frame(frame, bg=BG)
        btns.pack(anchor="w", pady=4)
        for label, cmd in (
            ("RUN", self._run),
            ("STOP", self._stop),
            ("STEP", self._step),
            ("RESET", self._reset),
            ("EXAMINE", self._examine),
            ("EX NEXT", self._examine_next),
            ("DEPOSIT", self._deposit),
            ("DEP NEXT", self._deposit_next),
            ("CLR TTY", self._clear_tty),
            ("OVERCLOCK", self._overclock),
        ):
            tk.Button(btns, text=label, command=cmd, bg="#4a4840", fg=TEXT, activebackground="#6a6458", relief=tk.RAISED).pack(side=tk.LEFT, padx=3)

    def _build_terminal(self) -> None:
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))
        tk.Label(wrap, text="SERIAL  (UART $C000) — click and type. RESET / CLR TTY wipe this view.", fg=DIM, bg=BG, font=("Courier", 10)).pack(anchor="w")
        self.term_font = tkfont.Font(family="Courier", size=12)
        self.term = tk.Text(
            wrap,
            bg="#0d0d0c",
            fg="#9cff9c",
            insertbackground="#9cff9c",
            font=self.term_font,
            wrap=tk.CHAR,
            height=14,
            undo=False,
        )
        self.term.pack(fill=tk.BOTH, expand=True)
        self.term.bind("<Key>", self._on_key)
        self.term.bind("<Button-1>", lambda e: self.term.focus_set())
        self.term.focus_set()

    def _wire_uart(self) -> None:
        def tx(ch: int) -> None:
            if ch == 8:
                self.term.delete("end-2c", "end-1c")
            elif ch in (10, 13):
                self.term.insert(tk.END, "\n")
            elif 32 <= ch < 127:
                self.term.insert(tk.END, chr(ch))
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
        if event.char:
            self.machine.uart.push_rx(event.char.encode("ascii", errors="ignore"))
        return "break"

    def _run(self) -> None:
        self.machine.running = True
        self.machine.clock.sync()

    def _stop(self) -> None:
        self.machine.running = False

    def _overclock(self) -> None:
        self.machine.clock.set_overclock(not self.machine.clock.overclock)

    def _step(self) -> None:
        self.machine.running = False
        self.machine.cpu.step_instruction()
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
        self.machine.running = True
        self.machine.clock.sync()
        self._clear_tty()
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

    def _refresh_lamps(self) -> None:
        s = sample(self.machine)
        self.addr_lamps.set(s.addr)
        self.data_lamps.set(s.data)
        self.ir_lamps.set(s.ir)
        flags = {
            "RUN": s.running and not s.wait,
            "WAIT": s.wait or not s.running,
            "I": s.flag_i,
            "IRQ": s.irq,
            "N": s.flag_n,
            "Z": s.flag_z,
            "C": s.flag_c,
            "V": s.flag_v,
        }
        for name, on in flags.items():
            self.canvas.itemconfig(self.stat_ids[name], fill=LED_ON if on else LED_OFF)
        self.hex_var.set(
            f"ADDR ${s.addr:04X}   DATA ${s.data:02X}   IR ${s.ir:02X}   "
            f"PC ${s.pc:04X}   A ${s.a:02X}   {s.phase}   "
            f"{'RUN' if s.running and not s.wait else 'STOP'}  "
            f"{self.machine.clock.label()}"
        )

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
