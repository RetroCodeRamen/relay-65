# -*- mode: python ; coding: utf-8 -*-
"""Frozen Relay-65 front panel for Windows and Linux.

From the repo root:
  pip install pyinstaller
  pyinstaller pack/relay65.spec
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT / "emulator"))
hidden = collect_submodules("relay65")
try:
    import tkinter  # noqa: F401

    hidden.extend(["tkinter", "tkinter.font"])
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "pack" / "entry.py")],
    pathex=[str(ROOT / "emulator")],
    binaries=[],
    datas=[
        (str(ROOT / "emulator" / "rom" / "monitor.s"), "rom"),
        (str(ROOT / "software" / "images" / "console.bin"), "images"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Relay-65",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
