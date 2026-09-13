"""Browser front panel + serial terminal. Used when tkinter is not installed."""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .leds import sample
from .panelops import deposit, deposit_next, examine, examine_next

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Relay-65</title>
<style>
  :root { --bg:#1c1c1a; --metal:#2c2c28; --on:#ff3030; --off:#4a1212; --text:#e8e0d0; --dim:#8a8070; }
  html,body { margin:0; background:var(--bg); color:var(--text); font-family: Helvetica, Arial, sans-serif; }
  h1 { margin:12px 16px 4px; font-size:20px; letter-spacing:.12em; }
  .sub { margin:0 16px 12px; color:var(--dim); font-size:13px; }
  #termwrap { margin:8px 16px 4px; }
  .panel { background:var(--metal); margin:8px 16px 16px; padding:14px 16px 10px; border-radius:6px; }
  .row { display:flex; align-items:center; gap:6px; margin:8px 0; flex-wrap:wrap; }
  .lab { width:48px; color:var(--dim); font: 12px ui-monospace, Courier, monospace; flex-shrink:0; }
  .caption { color:var(--dim); font: 12px ui-monospace, Courier, monospace; margin:0 0 6px; width:auto; }
  .lamp { width:14px; height:14px; border-radius:50%; background:var(--off); box-shadow: inset 0 1px 2px #000; }
  .lamp.on { background:var(--on); box-shadow:0 0 8px #ff4040; }
  .gap { width:10px; }
  .sw { width:16px; height:28px; background:#3a3a36; border-radius:3px; cursor:pointer; border:1px solid #111; }
  .sw.on { background:#ddd5c8; }
  .hex { font: 14px ui-monospace, Courier, monospace; margin:8px 16px; }
  .clocks { margin:4px 16px 10px; display:flex; gap:28px; flex-wrap:wrap; align-items:flex-end; }
  .clk-lab { color:var(--dim); font: 11px ui-monospace, Courier, monospace; letter-spacing:.06em; }
  .clk-val { font: 22px ui-monospace, Courier, monospace; color:var(--text); }
  .clk-note { margin:0 16px 8px; color:var(--dim); font: 12px Helvetica, Arial, sans-serif; }
  .btns { margin:10px 16px; display:flex; gap:8px; flex-wrap:wrap; }
  button { background:#4a4840; color:var(--text); border:1px solid #222; padding:6px 12px; cursor:pointer; }
  button:hover { background:#6a6458; }
  .hexin { background:#2a2a26; color:var(--text); font: 14px ui-monospace, Courier, monospace; width:4.5em; border:1px solid #444; }
  #term {
    width:100%; height:280px; min-height:280px; box-sizing:border-box;
    background:#0d0d0c; color:#9cff9c; font: 14px ui-monospace, Courier, monospace;
    border:1px solid #333; padding:8px; white-space:pre-wrap; overflow:auto; outline:none;
    cursor:text;
  }
  #term:focus { border-color:#6a8; }
</style>
</head>
<body>
  <h1>RELAY-65</h1>
  <p class="sub">Green box below is the UART. RUN starts, STOP pauses, STEP is one instruction, RESET rewinds to the program start without changing RUN/STOP. SPEED cycles RELAY (real coils) → 1s=1min (one PC second = one relay minute) → WARP (as fast as this PC).</p>
  <div id="termwrap">
    <div class="caption">SERIAL UART $C000 — click this box and type (or type anywhere except ADDR/DATA). CLR TTY wipes this view.</div>
    <pre id="term" tabindex="0"></pre>
  </div>
  <div class="panel">
    <div class="row" id="addrLamps"><span class="lab">ADDR</span></div>
    <div class="row" id="addrSw"><span class="lab">A SW</span></div>
    <div class="row" id="dataLamps"><span class="lab">DATA</span></div>
    <div class="row" id="dataSw"><span class="lab">D SW</span></div>
    <div class="row" id="irLamps"><span class="lab">IR</span></div>
    <div class="row" id="statLamps"><span class="lab">STAT</span></div>
  </div>
  <div class="hex" id="hex"></div>
  <div class="clocks">
    <div><div class="clk-lab">HOST (this PC, RUN on)</div><div class="clk-val" id="hostT">0.0s</div></div>
    <div><div class="clk-lab">REAL (relays)</div><div class="clk-val" id="realT">0.0s</div></div>
    <div><div class="clk-lab">WARP</div><div class="clk-val" id="warpT">—</div></div>
  </div>
  <p class="clk-note" id="clockNote">HOST is wall time while RUN is on. REAL is those same microsteps at the relay clock (default 20 ms each) — how long the hardware would have to run to match warp.</p>
  <div class="hex">
    ADDR $<input id="addrHex" class="hexin" maxlength="4" value="0000">
    DATA $<input id="dataHex" class="hexin" maxlength="2" value="00" style="width:2.5em">
    <button type="button" id="setSw">SET SWITCHES</button>
  </div>
  <div class="btns">
    <button data-cmd="run">RUN</button>
    <button data-cmd="stop">STOP</button>
    <button data-cmd="step">STEP</button>
    <button data-cmd="reset">RESET</button>
    <button data-cmd="examine">EXAMINE</button>
    <button data-cmd="examine_next">EX NEXT</button>
    <button data-cmd="deposit">DEPOSIT</button>
    <button data-cmd="deposit_next">DEP NEXT</button>
    <button data-cmd="clr_tty">CLR TTY</button>
    <button data-cmd="speed" id="speedBtn">SPEED</button>
  </div>
<script>
const addrL = mkLamps("addrLamps", 16);
const dataL = mkLamps("dataLamps", 8);
const irL = mkLamps("irLamps", 8);
const statNames = ["RUN","WAIT","I","IRQ","N","Z","C","V"];
const statL = mkNamed("statLamps", statNames);
const addrS = mkSw("addrSw", 16);
const dataS = mkSw("dataSw", 8);
let serial = "";
let termSeq = 0;

function mkLamps(id, n) {
  const row = document.getElementById(id);
  const els = [];
  for (let i = 0; i < n; i++) {
    if (i && i % 8 === 0) { const g = document.createElement("div"); g.className="gap"; row.appendChild(g); }
    const d = document.createElement("div"); d.className = "lamp"; row.appendChild(d); els.push(d);
  }
  return els;
}
function mkNamed(id, names) {
  const row = document.getElementById(id);
  const els = {};
  names.forEach(n => {
    const wrap = document.createElement("div"); wrap.style.textAlign="center";
    const lab = document.createElement("div"); lab.textContent=n; lab.style.font="10px Courier"; lab.style.color="#8a8070";
    const d = document.createElement("div"); d.className="lamp"; wrap.appendChild(lab); wrap.appendChild(d);
    row.appendChild(wrap); els[n]=d;
  });
  return els;
}
function mkSw(id, n) {
  const row = document.getElementById(id);
  const els = [];
  for (let i = 0; i < n; i++) {
    if (i && i % 8 === 0) { const g = document.createElement("div"); g.className="gap"; row.appendChild(g); }
    const wrap = document.createElement("div");
    wrap.style.textAlign = "center";
    const lab = document.createElement("div");
    lab.textContent = String(n - 1 - i);
    lab.style.font = "9px Courier";
    lab.style.color = "#8a8070";
    const d = document.createElement("div"); d.className = "sw";
    d.onclick = () => { d.classList.toggle("on"); syncHexFromSw(); };
    wrap.appendChild(lab); wrap.appendChild(d);
    row.appendChild(wrap); els.push(d);
  }
  return els;
}
function setSw(els, val) {
  const n = els.length;
  els.forEach((el, i) => el.classList.toggle("on", !!(val & (1 << (n-1-i)))));
}
function syncHexFromSw() {
  document.getElementById("addrHex").value = swVal(addrS).toString(16).toUpperCase().padStart(4,"0");
  document.getElementById("dataHex").value = swVal(dataS).toString(16).toUpperCase().padStart(2,"0");
}
function parseHex(s) {
  const v = parseInt(String(s).trim() || "0", 16);
  return Number.isNaN(v) ? 0 : v;
}
function applyHex() {
  const a = parseHex(document.getElementById("addrHex").value);
  const d = parseHex(document.getElementById("dataHex").value);
  setSw(addrS, a & 0xFFFF);
  setSw(dataS, d & 0xFF);
  syncHexFromSw();
}
function swVal(els) {
  let v = 0;
  els.forEach((el, i) => { if (el.classList.contains("on")) v |= 1 << (els.length-1-i); });
  return v;
}
function setLamps(els, val) {
  const n = els.length;
  els.forEach((el, i) => el.classList.toggle("on", !!(val & (1 << (n-1-i)))));
}

document.getElementById("setSw").onclick = applyHex;
document.getElementById("addrHex").addEventListener("keydown", e => { if (e.key === "Enter") applyHex(); });
document.getElementById("dataHex").addEventListener("keydown", e => { if (e.key === "Enter") applyHex(); });

document.querySelectorAll("button[data-cmd]").forEach(b => {
  b.onclick = async () => {
    applyHex();
    const r = await fetch("/api/cmd", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({cmd:b.dataset.cmd, addr:swVal(addrS), data:swVal(dataS)})
    });
    const j = await r.json();
    if (j.addr != null) { setSw(addrS, j.addr); syncHexFromSw(); }
  };
});

const term = document.getElementById("term");
term.focus();
function sendKey(e) {
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  let s = null;
  if (e.key === "Enter") s = "\r";
  else if (e.key === "Backspace") s = "\b";
  else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) s = e.key;
  if (!s) return;
  e.preventDefault();
  fetch("/api/key", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({data:s})});
}
document.addEventListener("keydown", sendKey);
term.addEventListener("mousedown", () => term.focus());

async function poll() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    setLamps(addrL, s.addr);
    setLamps(dataL, s.data);
    setLamps(irL, s.ir);
    statNames.forEach(n => statL[n].classList.toggle("on", !!s.stat[n]));
    document.getElementById("hex").textContent =
      `ADDR $${s.addr.toString(16).padStart(4,"0")}  DATA $${s.data.toString(16).padStart(2,"0")}  IR $${s.ir.toString(16).padStart(2,"0")}  PC $${s.pc.toString(16).padStart(4,"0")}  A $${s.a.toString(16).padStart(2,"0")}  ${s.phase}  ${s.halted ? "HALTED" : (s.running && !s.wait ? "RUN" : "STOP")}  ${s.clock}`;
    if (s.host) document.getElementById("hostT").textContent = s.host;
    if (s.real) document.getElementById("realT").textContent = s.real;
    if (s.warp) document.getElementById("warpT").textContent = s.warp;
    if (s.clock_note) document.getElementById("clockNote").textContent = s.clock_note;
    if (s.clock) document.getElementById("speedBtn").textContent = s.clock;
    if (typeof s.term_seq === "number" && s.term_seq !== termSeq) {
      termSeq = s.term_seq;
      serial = "";
      term.textContent = "";
    }
    if (s.serial && s.serial.length) {
      serial += s.serial;
      term.textContent = serial.replace(/\r/g,"\n");
      term.scrollTop = term.scrollHeight;
    }
  } catch (err) {}
}
setInterval(poll, 50);
poll();
</script>
</body>
</html>
"""


class _State:
    def __init__(self, machine, burst: int) -> None:
        self.machine = machine
        self.burst = burst
        self.lock = threading.Lock()
        self.serial = bytearray()
        self.term_seq = 0
        self._alive = True

        def tx(ch: int) -> None:
            self.serial.append(ch)
            try:
                sys.stdout.buffer.write(bytes([ch & 0xFF]))
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                pass

        machine.uart.on_tx = tx
        self.thread = threading.Thread(target=self._cpu_loop, daemon=True)
        self.thread.start()

    def _cpu_loop(self) -> None:
        clock = self.machine.clock
        clock.sync()
        was_running = False
        while self._alive:
            with self.lock:
                running = self.machine.running
                if running and not was_running:
                    clock.sync()
                was_running = running
                if running and not self.machine.cpu.halted:
                    if clock.overclock:
                        for _ in range(self.burst):
                            self.machine.step()
                            if not self.machine.running or self.machine.cpu.halted:
                                break
                    else:
                        n = clock.due_steps()
                        for _ in range(n):
                            self.machine.step()
                            clock.account(1)
                            if not self.machine.running:
                                break
            time.sleep(0.0 if clock.overclock else 0.01)

    def stop(self) -> None:
        self._alive = False


def run_web(machine, burst: int = 800, start_running: bool = False, host: str = "127.0.0.1", port: int = 8065) -> int:
    machine.clock.reset_runtime()
    machine.running = start_running
    st = _State(machine, burst)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args) -> None:
            pass

        def _json(self, obj, code=200) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/state":
                with st.lock:
                    s = sample(st.machine)
                    out = bytes(st.serial)
                    st.serial.clear()
                    rt = st.machine.clock.runtime_fields()
                    clock_note = (
                        f"HOST is wall time while RUN is on. REAL is those same microsteps "
                        f"at {rt['real_ms']:.0f} ms each — how long the relays would need in real mode."
                    )
                self._json(
                    {
                        "addr": s.addr,
                        "data": s.data,
                        "ir": s.ir,
                        "pc": s.pc,
                        "a": s.a,
                        "phase": s.phase,
                        "clock": st.machine.clock.label(),
                        "host": rt["host"],
                        "real": rt["real"],
                        "warp": rt["warp"],
                        "clock_note": clock_note,
                        "running": s.running,
                        "wait": s.wait,
                        "halted": st.machine.cpu.halted,
                        "stat": {
                            "RUN": s.running and not s.wait,
                            "WAIT": s.wait or not s.running,
                            "I": s.flag_i,
                            "IRQ": s.irq,
                            "N": s.flag_n,
                            "Z": s.flag_z,
                            "C": s.flag_c,
                            "V": s.flag_v,
                        },
                        "serial": out.decode("ascii", errors="replace"),
                        "term_seq": st.term_seq,
                    }
                )
                return
            self.send_error(404)

        def do_POST(self) -> None:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            path = urlparse(self.path).path
            extra: dict = {}
            with st.lock:
                if path == "/api/key":
                    st.machine.uart.push_rx(body.get("data", ""))
                elif path == "/api/cmd":
                    extra = _do_cmd(st, body)
            self._json({"ok": True, **extra})

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Relay-65 GUI  {url}   {machine.clock.label()}   (Ctrl-C to stop)", flush=True)
    threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        st.stop()
        httpd.server_close()
    return 0


def _do_cmd(st, body: dict) -> dict:
    machine = st.machine
    cmd = body.get("cmd")
    addr = int(body.get("addr") or 0) & 0xFFFF
    data = int(body.get("data") or 0) & 0xFF
    extra: dict = {}

    def wipe_tty() -> None:
        machine.uart.clear()
        st.serial.clear()
        st.term_seq += 1

    if cmd == "run":
        machine.running = True
        machine.clock.sync()
    elif cmd == "stop":
        machine.running = False
    elif cmd in ("speed", "overclock"):
        machine.clock.cycle_speed()
    elif cmd == "step":
        machine.running = False
        machine.cpu.step_instruction()
    elif cmd == "reset":
        machine.restart_loaded()
    elif cmd == "clr_tty":
        wipe_tty()
    elif cmd == "examine":
        extra["addr"] = examine(machine, addr)
    elif cmd == "examine_next":
        extra["addr"] = examine_next(machine, addr)
    elif cmd == "deposit":
        extra["addr"] = deposit(machine, addr, data)
    elif cmd == "deposit_next":
        extra["addr"] = deposit_next(machine, addr, data)
    return extra
