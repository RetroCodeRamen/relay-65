"""Relay-65 emulator.

  ./relay65 --gui --load software/cc65/hello.bin
  # window: lamps + paddle switches on top, serial terminal below
"""

from __future__ import annotations

import argparse
import select
import sys
import time
from pathlib import Path

from .assemble import assemble
from .leds import sample
from .machine import Machine
from .mmap import ROM_BASE
from .panel import FrontPanel
from .serialport import SerialPort

ROOT = Path(__file__).resolve().parent.parent
ROM_SOURCE = ROOT / "rom" / "monitor.s"


def build_monitor():
    img = assemble(ROM_SOURCE.read_text(), default_origin=ROM_BASE)
    return img.origin, img.data


def pump_stdin(machine: Machine) -> None:
    if not sys.stdin.isatty():
        return
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if not r:
        return
    data = sys.stdin.buffer.read1(256)
    if data:
        machine.uart.push_rx(data)


def load_machine(machine: Machine, args) -> None:
    origin, rom = build_monitor()
    machine.load_image(origin, rom)
    entry = None
    if args.program:
        img = assemble(args.program.read_text())
        machine.load_image(img.origin, img.data)
        entry = img.origin
        machine.entry = img.origin
    if args.load:
        machine.load_ram(args.load_addr, args.load.read_bytes())
        entry = args.load_addr
        machine.entry = args.load_addr
    if args.fuzix:
        disk = args.disk.read_bytes() if args.disk else None
        machine.load_fuzix(args.fuzix.read_bytes(), disk)
        entry = machine.entry
    elif args.disk:
        machine.memory.ide.load_image(args.disk.read_bytes())
    machine.reset()
    if args.entry is not None:
        machine.entry = args.entry & 0xFFFF
        machine.cpu.pc = machine.entry
        machine.cpu.state = "FETCH"
        machine.cpu.ustep = 0
    elif entry is not None:
        machine.cpu.pc = entry
        machine.cpu.state = "FETCH"
        machine.cpu.ustep = 0


def run_serial(machine: Machine, args) -> int:
    def tx(ch: int) -> None:
        sys.stdout.buffer.write(bytes([ch]))
        sys.stdout.buffer.flush()

    machine.uart.on_tx = tx
    last_ins = 0
    machine.clock.reset_runtime()
    machine.clock.sync()
    try:
        while not machine.cpu.halted:
            if sys.stdin.isatty():
                pump_stdin(machine)
            machine.step()
            machine.clock.account(1)
            machine.clock.sleep_until_due()
            if args.leds and machine.cpu.instructions - last_ins >= args.leds_every:
                last_ins = machine.cpu.instructions
                print(sample(machine).one_line(), file=sys.stderr)
            if args.max is not None and machine.cpu.instructions >= args.max:
                if args.leds:
                    print(sample(machine).text(), file=sys.stderr)
                break
    except KeyboardInterrupt:
        print("\n" + sample(machine).text(), file=sys.stderr)
        print("[STOP]", file=sys.stderr)
    return 0


def run_panel(machine: Machine, args) -> int:
    serial = SerialPort(args.serial_port)
    serial.attach_tx(machine)
    panel = FrontPanel(machine)
    machine.clock.reset_runtime()
    machine.running = bool(args.run)
    machine.clock.sync()
    panel.enter_cbreak()
    print(f"serial tcp 127.0.0.1:{args.serial_port}  (nc 127.0.0.1 {args.serial_port})", file=sys.stderr)
    print(machine.clock.label(), file=sys.stderr)
    if not machine.running:
        print("STOP — press R to run, or start with --run", file=sys.stderr)
    try:
        steps = 0
        was_running = machine.running
        while not machine.cpu.halted:
            serial.pump_rx(machine)
            if not panel.poll_key():
                break
            if machine.running and not was_running:
                machine.clock.sync()
            was_running = machine.running
            if machine.running:
                if machine.clock.overclock:
                    for _ in range(args.burst):
                        machine.step()
                        if not machine.running:
                            break
                else:
                    n = machine.clock.due_steps()
                    if n == 0:
                        time.sleep(0.004)
                    for _ in range(n):
                        machine.step()
                        machine.clock.account(1)
                        if not machine.running:
                            break
            else:
                time.sleep(0.016)
            steps += 1
            if steps % 64 == 0:
                sys.stderr.write("\033[2J\033[H")
                sys.stderr.write(panel.render() + "\n")
                sys.stderr.flush()
            if args.max is not None and machine.cpu.instructions >= args.max:
                break
    except KeyboardInterrupt:
        pass
    finally:
        panel.leave_cbreak()
        serial.close()
        print("\n" + sample(machine).text(), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Relay-65 microcoded 6502 emulator")
    p.add_argument("--program", type=Path, help="assemble a .s file into RAM")
    p.add_argument("--load", type=Path, help="load a raw binary (cc65 output) into RAM")
    p.add_argument("--load-addr", type=lambda s: int(s, 0), default=0x0200)
    p.add_argument(
        "--fuzix",
        type=Path,
        help="put this kernel on a CF card at LBA 1 and close the autoboot jumper",
    )
    p.add_argument("--disk", type=Path, help="CompactFlash image for slot 0 ($C100)")
    p.add_argument("--entry", type=lambda s: int(s, 0), help="front-panel load of PC")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--max", type=int, default=None)
    p.add_argument("--assemble-only", type=Path)
    p.add_argument(
        "--dump-microcode",
        type=Path,
        nargs="?",
        const=Path("emulator/rom/microcode"),
        help="write packed FETCH/RESET/IRQ/NMI/execute EEPROM images",
    )
    p.add_argument("--leds", action="store_true", help="print * / . lamps on stderr (Altair-style)")
    p.add_argument("--leds-every", type=int, default=256, help="instructions between --leds lines")
    p.add_argument("--gui", action="store_true", help="graphical panel + serial terminal window")
    p.add_argument("--panel", action="store_true", help="text lamps/switches; serial on TCP")
    p.add_argument("--run", action="store_true", help="start RUN (panel defaults to STOP, like power-on)")
    p.add_argument("--serial-port", type=int, default=6502)
    p.add_argument("--burst", type=int, default=8000, help="microsteps per overclocked panel refresh")
    p.add_argument(
        "--overclock",
        action="store_true",
        help="run as fast as the host (skip relay operate/release waits)",
    )
    p.add_argument(
        "--minute",
        action="store_true",
        help="1 host second = 1 minute of relay time (60×). SPEED on the panel cycles RELAY / 1s=1min / WARP",
    )
    p.add_argument(
        "--realtime",
        action="store_true",
        help="force relay-timed clock even with --max",
    )
    p.add_argument(
        "--timing",
        choices=("leeway", "datasheet"),
        default="leeway",
        help="leeway=10ms per coil change (default); datasheet=6ms operate + 4ms release",
    )
    p.add_argument("--phase-ms", type=float, default=None, help="override ms per Φ0/Φ1 coil change")
    args = p.parse_args(argv)

    if args.assemble_only:
        img = assemble(args.assemble_only.read_text())
        out = args.assemble_only.with_suffix(".bin")
        out.write_bytes(img.data)
        print(f"wrote {out} origin=${img.origin:04X} {len(img.data)} bytes")
        return 0

    if args.dump_microcode:
        from .eeprom import ControlStore

        store = ControlStore.from_isa()
        dest = args.dump_microcode
        dest.mkdir(parents=True, exist_ok=True)
        for name, blob in (
            ("fetch.bin", store.fetch),
            ("reset.bin", store.reset),
            ("irq.bin", store.irq),
            ("nmi.bin", store.nmi),
            ("execute.bin", store.execute),
        ):
            path = dest / name
            path.write_bytes(blob)
            print(f"wrote {path} {len(blob)} bytes")
        return 0

    machine = Machine()
    load_machine(machine, args)
    interactive = bool(args.gui or args.panel or (sys.stdin.isatty() and args.max is None))
    if args.overclock or (not args.realtime and not interactive):
        speed = "warp"
    elif args.minute:
        speed = "minute"
    else:
        speed = "relay"
    machine.clock.configure(
        speed=speed,
        datasheet=args.timing == "datasheet",
        phase_ms=args.phase_ms,
    )
    if args.gui:
        return _run_gui(machine, burst=args.burst, start_running=args.run)
    if args.panel:
        return run_panel(machine, args)
    return run_serial(machine, args)


def _run_gui(machine: Machine, burst: int, start_running: bool) -> int:
    try:
        import tkinter  # noqa: F401

        from .gui import run_gui

        return run_gui(machine, burst=burst, start_running=start_running)
    except ImportError:
        from .webui import run_web

        print("tkinter not installed — serial is the green box at http://127.0.0.1:8065", file=sys.stderr)
        print("(UART is also copied to this terminal.) RUN starts, STOP pauses, RESET rewinds to the loaded program.", file=sys.stderr)
        return run_web(machine, burst=burst, start_running=start_running)


if __name__ == "__main__":
    raise SystemExit(main())
