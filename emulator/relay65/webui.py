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
  :root {
    --bg: #0c1016;
    --bg-2: #141c28;
    --glass: linear-gradient(180deg, rgba(72,96,128,0.28) 0%, rgba(18,26,38,0.92) 38%, rgba(12,16,22,0.96) 100%);
    --glass-cpu: linear-gradient(180deg, rgba(120,180,220,0.30) 0%, rgba(18,32,46,0.90) 42%, rgba(10,16,24,0.96) 100%);
    --glass-machine: linear-gradient(180deg, rgba(120,90,70,0.26) 0%, rgba(26,22,26,0.93) 40%, rgba(12,12,14,0.97) 100%);
    --edge: rgba(180,210,240,0.22);
    --edge-in: rgba(255,255,255,0.14);
    --text: #eef4fa;
    --dim: #8aa0b8;
    --cyan: #5ec8e8;
    --cyan-dim: #3a88a8;
    --orange: #f0a050;
    --on: #ff2a28;
    --off: #280808;
    --term-fg: #c6e8c0;
    --term-bg: #070b10;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    height: 100%;
    overflow: hidden;
    color: var(--text);
    font-family: "Segoe UI", "Trebuchet MS", Calibri, sans-serif;
    background:
      radial-gradient(1200px 480px at 50% -80px, rgba(80,160,220,0.22), transparent 70%),
      radial-gradient(800px 400px at 100% 100%, rgba(240,120,40,0.06), transparent 55%),
      linear-gradient(180deg, #152030 0%, var(--bg) 28%, #080a0e 100%);
  }
  .shell {
    height: 100vh;
    height: 100dvh;
    max-width: 1480px;
    margin: 0 auto;
    padding: 6px 14px 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow: hidden;
  }
  .brand {
    display: flex; align-items: center; gap: 10px;
    flex: 0 0 auto;
    min-width: 0;
  }
  .brand-mark {
    width: 8px; height: 26px; border-radius: 2px; flex-shrink: 0;
    background: linear-gradient(180deg, #9ae8ff, var(--cyan) 40%, #1a6080);
    box-shadow: 0 0 12px rgba(94,200,232,0.55);
  }
  h1 {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.22em;
    color: #f6fbff;
    text-shadow: 0 0 18px rgba(94,200,232,0.35);
    flex-shrink: 0;
  }
  .sub {
    margin: 0;
    color: var(--dim);
    font-size: 11px;
    letter-spacing: 0.01em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  #termwrap {
    position: relative;
    flex: 5 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 5px 8px 6px;
    border-radius: 8px;
    background: var(--glass);
    border: 1px solid var(--edge);
    box-shadow:
      inset 0 1px 0 var(--edge-in),
      0 8px 24px rgba(0,0,0,0.45);
  }
  .caption {
    color: var(--cyan-dim);
    font: 10px Consolas, "Cascadia Mono", ui-monospace, monospace;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 0 0 4px;
    flex: 0 0 auto;
  }
  #term {
    position: relative;
    width: 100%;
    flex: 1 1 auto;
    height: auto;
    min-height: 0;
    background: var(--term-bg);
    color: var(--term-fg);
    font: 23px Consolas, "Cascadia Mono", ui-monospace, monospace;
    border: 1px solid #0a1218;
    border-radius: 4px;
    padding: 6px 8px;
    white-space: pre-wrap;
    overflow: auto;
    outline: none;
    cursor: text;
    box-shadow: inset 0 2px 10px rgba(0,0,0,0.65), inset 0 0 40px rgba(40,80,60,0.12);
  }
  #term:focus { border-color: rgba(94,200,232,0.45); }
  #termwrap::after {
    content: "";
    pointer-events: none;
    position: absolute;
    left: 9px; right: 9px; top: 24px; bottom: 7px;
    border-radius: 4px;
    background: repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.018) 0px,
      rgba(255,255,255,0.018) 1px,
      transparent 1px,
      transparent 3px
    );
  }
  .panels {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    flex: 6 1 0;
    min-height: 0;
    align-items: stretch;
  }
  .col { min-width: 0; display: flex; flex-direction: column; height: 100%; }
  .sect {
    margin: 0 2px 3px;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.18em;
    color: #d8ecf8;
    flex: 0 0 auto;
  }
  .sect-machine { color: #ecd8c8; }
  .sect-cpu { color: #d0eefc; }
  .clk-note {
    margin: 0;
    color: var(--dim);
    font-size: 11px;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .panel {
    flex: 1 1 auto;
    min-height: 0;
    padding: 12px 17px 14px 0;
    border-radius: 8px;
    border: 1px solid var(--edge);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 7px;
    box-shadow:
      inset 0 1px 0 var(--edge-in),
      0 10px 28px rgba(0,0,0,0.4);
  }
  .machine-panel {
    background: var(--glass-machine);
    box-shadow:
      inset 0 1px 0 rgba(255,200,160,0.10),
      inset 0 0 40px rgba(40,20,10,0.25),
      0 10px 28px rgba(0,0,0,0.4);
  }
  .cpu-panel {
    background: var(--glass-cpu);
    box-shadow:
      inset 0 1px 0 rgba(160,220,255,0.16),
      inset 0 0 36px rgba(20,50,80,0.2),
      0 10px 28px rgba(0,0,0,0.4);
  }
  .pair { display: flex; gap: 8px 27px; align-items: center; min-width: 0; }
  .panel > .row, .panel > .pair { margin-left: -18px; }
  .machine-panel #irLamps,
  .machine-panel #statLamps { margin-left: -40px; }
  .cpu-panel > .row, .cpu-panel > .pair { margin-left: -43px; }
  .cpu-panel #xLamps,
  .cpu-panel #spLamps { margin-left: -30px; }
  .pair > .row { flex: 1 1 0; min-width: 0; }
  .row { display: flex; align-items: center; gap: 7px; margin: 0; flex-wrap: nowrap; }
  .lab {
    width: 96px;
    color: var(--dim);
    font: 14px Consolas, "Cascadia Mono", ui-monospace, monospace;
    letter-spacing: 0.04em;
    flex-shrink: 0;
    text-align: right;
  }
  .hexv {
    font: 19px Consolas, "Cascadia Mono", ui-monospace, monospace;
    color: #f4f8fc;
    margin-left: 11px;
    min-width: 3.4em;
    text-shadow: 0 0 8px rgba(94,200,232,0.25);
    flex-shrink: 0;
  }
  .bitlab {
    font: 12px Consolas, "Cascadia Mono", ui-monospace, monospace;
    color: #7a90a4;
    letter-spacing: 0;
  }
  .lamp {
    width: 22px; height: 22px;
    margin: 0 auto;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #4a1818, var(--off) 68%);
    border: 1px solid #1a0404;
    box-shadow: inset 0 1px 2px rgba(255,180,180,0.12), inset 0 -2px 3px #000;
    transition: background 80ms linear, box-shadow 80ms linear;
    flex-shrink: 0;
  }
  .lamp.on {
    background: radial-gradient(circle at 35% 30%, #ffb0a8, var(--on) 55%, #8a0000);
    border-color: #ff6a60;
    box-shadow: 0 0 6px 1px rgba(255,50,40,0.5), inset 0 1px 1px rgba(255,255,255,0.35);
  }
  .gap { width: 13px; flex-shrink: 0; }
  .sw {
    width: 20px; height: 32px;
    border-radius: 3px;
    cursor: pointer;
    background: linear-gradient(180deg, #2a3340, #151a22);
    border: 1px solid #0a0d12;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 2px 2px rgba(0,0,0,0.4);
    transition: background 80ms linear, box-shadow 80ms linear;
    flex-shrink: 0;
  }
  .sw.on {
    background: linear-gradient(180deg, #e8f2fa, #9ab8cc);
    border-color: #7aa0b8;
    box-shadow: 0 0 8px rgba(94,200,232,0.35), inset 0 1px 0 #fff;
  }
  .dock { flex: 0 0 auto; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .status-row {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
  }
  .status {
    margin: 0;
    padding: 4px 10px;
    border-radius: 6px;
    background: rgba(8,12,18,0.55);
    border: 1px solid rgba(94,200,232,0.18);
    font: 12px Consolas, "Cascadia Mono", ui-monospace, monospace;
    color: var(--cyan);
    letter-spacing: 0.04em;
    flex: 1 1 auto;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .clocks {
    margin: 0;
    display: flex;
    gap: 16px;
    flex-wrap: nowrap;
    align-items: flex-end;
    flex-shrink: 0;
  }
  .clk-lab {
    color: var(--dim);
    font: 9px "Segoe UI", sans-serif;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .clk-val {
    font: 15px Consolas, "Cascadia Mono", ui-monospace, monospace;
    color: var(--text);
    text-shadow: 0 0 12px rgba(94,200,232,0.2);
  }
  .ctrl-bar {
    margin: 0;
    display: flex;
    flex-direction: column;
    flex-wrap: nowrap;
    gap: 5px;
    align-items: stretch;
    min-width: 0;
  }
  .ctrl-group {
    padding: 6px 10px 7px;
    border-radius: 8px;
    background: var(--glass);
    border: 1px solid var(--edge);
    box-shadow: inset 0 1px 0 var(--edge-in);
    width: 100%;
  }
  .ctrl-group.clock, .ctrl-group.memory { flex: 0 0 auto; min-width: 0; }
  .ctrl-lab {
    color: var(--orange);
    font: 10px "Segoe UI", sans-serif;
    letter-spacing: 0.16em;
    margin-bottom: 4px;
  }
  .btns { display: flex; gap: 6px; flex-wrap: nowrap; }
  .btns button { flex: 1 1 0; }
  .mem-row { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; }
  .mem-row button { flex: 1 1 0; }
  .mem-lab { white-space: nowrap; flex-shrink: 0; }
  button {
    appearance: none;
    font: 12px "Segoe UI", sans-serif;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #f8fbff;
    background: linear-gradient(180deg, #5a78a0 0%, #2c4058 48%, #1c2a3a 100%);
    border: 1px solid #8ab0c8;
    border-bottom-color: #0a1018;
    border-radius: 4px;
    padding: 6px 12px;
    cursor: pointer;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.28), 0 2px 4px rgba(0,0,0,0.4);
    white-space: nowrap;
  }
  button:hover {
    background: linear-gradient(180deg, #5a88a8 0%, #2a4860 50%, #1c3040 100%);
    border-color: var(--cyan);
  }
  button:active {
    transform: translateY(1px);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.45);
  }
  button:focus-visible { outline: 1px solid var(--cyan); outline-offset: 1px; }
  .hexin {
    background: linear-gradient(180deg, #0e141c, #1a2430);
    color: #f4f8fc;
    font: 14px Consolas, "Cascadia Mono", ui-monospace, monospace;
    width: 4.4em;
    border: 1px solid #3a5068;
    border-radius: 4px;
    padding: 5px 7px;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.45);
    flex-shrink: 0;
  }
  .hexin:focus { outline: none; border-color: var(--cyan); }
  #statLamps > div { min-width: 34px; }
</style>
</head>
<body>
<div class="shell">
  <header class="brand">
    <div class="brand-mark"></div>
    <h1>RELAY-65</h1>
    <p class="sub">UART $C000 · MACHINE = relay bus/sequencer · 6502 = A X Y SP P PC · STEP ROW = EEPROM word · STEP OP = instruction</p>
  </header>
  <div id="termwrap">
    <div class="caption">Serial · UART $C000 · Return = CR · Backspace = $08 · Delete = $7F</div>
    <pre id="term" tabindex="0"></pre>
  </div>
  <div class="dock">
  <div class="ctrl-bar">
    <div class="ctrl-group clock">
      <div class="ctrl-lab">Clock</div>
      <div class="btns">
        <button data-cmd="run">RUN</button>
        <button data-cmd="stop">STOP</button>
        <button data-cmd="step_row">STEP ROW</button>
        <button data-cmd="step_op">STEP OP</button>
        <button data-cmd="reset">RESET</button>
        <button data-cmd="speed" id="speedBtn">SPEED</button>
      </div>
    </div>
    <div class="ctrl-group memory">
      <div class="ctrl-lab">Memory</div>
      <div class="mem-row">
        <span class="mem-lab">ADDR $</span><input id="addrHex" class="hexin" maxlength="4" value="0000">
        <span class="mem-lab">DATA $</span><input id="dataHex" class="hexin" maxlength="2" value="00" style="width:2.8em">
        <button type="button" id="setSw">SET SW</button>
        <button data-cmd="examine">EXAMINE</button>
        <button data-cmd="examine_next">EX NEXT</button>
        <button data-cmd="deposit">DEPOSIT</button>
        <button data-cmd="deposit_next">DEP NEXT</button>
        <button data-cmd="clr_tty">CLR TTY</button>
      </div>
    </div>
  </div>
  <div class="status-row">
    <div class="status" id="hex"></div>
    <div class="clocks">
      <div><div class="clk-lab">HOST</div><div class="clk-val" id="hostT">0.0s</div></div>
      <div><div class="clk-lab">REAL</div><div class="clk-val" id="realT">0.0s</div></div>
      <div><div class="clk-lab">WARP</div><div class="clk-val" id="warpT">—</div></div>
    </div>
  </div>
  <p class="clk-note" id="clockNote">HOST is wall time while RUN is on. REAL is those same microsteps at the relay clock (default 20 ms each) — how long the hardware would have to run to match warp.</p>
  </div>
  <div class="panels">
  <div class="col">
  <div class="sect sect-machine" title="MAR is the address register. Fetch puts PC on A[15:0] when ADDR_PC is on. BUS is the last internal-bus byte.">MACHINE</div>
  <div class="panel machine-panel">
    <div class="row" id="addrLamps"><span class="lab">MAR</span></div>
    <div class="row" id="addrSw"><span class="lab">ADDR SW</span></div>
    <div class="pair">
      <div class="row" id="dataLamps"><span class="lab">BUS</span></div>
      <div class="row" id="irLamps"><span class="lab">IR</span></div>
    </div>
    <div class="pair">
      <div class="row" id="dataSw"><span class="lab">DATA SW</span></div>
      <div class="row" id="statLamps"><span class="lab">SEQ</span></div>
    </div>
  </div>
  </div>
  <div class="col">
  <div class="sect sect-cpu" title="Architectural registers. P bits left-to-right: N V U B D I Z C (B is not stored; U is forced 1).">6502</div>
  <div class="panel cpu-panel">
    <div class="row" id="pcLamps"><span class="lab">PC</span></div>
    <div class="pair">
      <div class="row" id="aLamps"><span class="lab">A</span></div>
      <div class="row" id="xLamps"><span class="lab">X</span></div>
    </div>
    <div class="pair">
      <div class="row" id="yLamps"><span class="lab">Y</span></div>
      <div class="row" id="spLamps"><span class="lab">SP</span></div>
    </div>
    <div class="row" id="pLamps"><span class="lab">P</span></div>
  </div>
  </div>
  </div>
</div>
<script>
const addrL = mkLamps("addrLamps", 16, true);
const dataL = mkLamps("dataLamps", 8, true);
const irL = mkLamps("irLamps", 8, true);
const pcL = mkLamps("pcLamps", 16, true);
const aL = mkLamps("aLamps", 8, true);
const xL = mkLamps("xLamps", 8, true);
const yL = mkLamps("yLamps", 8, true);
const spL = mkLamps("spLamps", 8, true);
const pL = mkLamps("pLamps", 8, false, ["N","V","U","B","D","I","Z","C"]);
const statNames = ["RUN","WAIT","IRQ"];
const statL = mkNamed("statLamps", statNames);
const addrS = mkSw("addrSw", 16);
const dataS = mkSw("dataSw", 8);
let serial = "";
let termSeq = 0;

function mkLamps(id, n, nums, names) {
  const row = document.getElementById(id);
  const els = [];
  for (let i = 0; i < n; i++) {
    if (i && i % 8 === 0) { const g = document.createElement("div"); g.className="gap"; row.appendChild(g); }
    const wrap = document.createElement("div");
    wrap.style.textAlign = "center";
    if (names || nums) {
      const lab = document.createElement("div");
      lab.className = "bitlab";
      lab.textContent = names ? names[i] : String(n-1-i);
      wrap.appendChild(lab);
    }
    const d = document.createElement("div"); d.className = "lamp"; wrap.appendChild(d);
    row.appendChild(wrap); els.push(d);
  }
  const hx = document.createElement("span"); hx.className = "hexv"; hx.id = id + "Hex"; hx.textContent = "$00";
  row.appendChild(hx);
  return els;
}
function mkNamed(id, names) {
  const row = document.getElementById(id);
  const els = {};
  names.forEach(n => {
    const wrap = document.createElement("div"); wrap.style.textAlign="center";
    const lab = document.createElement("div"); lab.className="bitlab"; lab.textContent=n;
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
    lab.className = "bitlab";
    lab.textContent = String(n - 1 - i);
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
  else if (e.key === "Delete") s = "\x7f";
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
    setLamps(pcL, s.pc);
    setLamps(aL, s.a);
    setLamps(xL, s.x);
    setLamps(yL, s.y);
    setLamps(spL, s.sp);
    setLamps(pL, s.p);
    const hx = (id, v, w) => { const el = document.getElementById(id); if (el) el.textContent = "$" + v.toString(16).toUpperCase().padStart(w,"0"); };
    hx("addrLampsHex", s.addr, 4);
    hx("dataLampsHex", s.data, 2);
    hx("irLampsHex", s.ir, 2);
    hx("pcLampsHex", s.pc, 4);
    hx("aLampsHex", s.a, 2);
    hx("xLampsHex", s.x, 2);
    hx("yLampsHex", s.y, 2);
    hx("spLampsHex", s.sp, 2);
    hx("pLampsHex", s.p, 2);
    statNames.forEach(n => statL[n].classList.toggle("on", !!s.stat[n]));
    document.getElementById("hex").textContent =
      `${s.phase}  u=${s.ustep}  ${s.halted ? "HALTED" : (s.running && !s.wait ? "RUN" : "STOP")}  ${s.clock}`;
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
      for (const ch of s.serial) {
        if (ch === "\b" || ch === "\x7f") {
          if (serial.length) serial = serial.slice(0, -1);
        } else {
          serial += ch;
        }
      }
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
            ch &= 0xFF
            if ch in (8, 10, 13, 127) or 32 <= ch < 127:
                self.serial.append(ch)
            try:
                sys.stdout.buffer.write(bytes([ch]))
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
                        "x": s.x,
                        "y": s.y,
                        "sp": s.sp,
                        "p": s.p,
                        "ustep": s.ustep,
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
                            "IRQ": s.irq,
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
    elif cmd in ("step_row", "step"):
        machine.running = False
        machine.step_micro()
    elif cmd == "step_op":
        machine.running = False
        machine.step_instruction()
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
