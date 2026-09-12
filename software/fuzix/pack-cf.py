#!/usr/bin/env python3
"""Write a CompactFlash image a PC would burn for the real slot."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "emulator"))

from relay65.diskimg import build_cf  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: pack-cf.py fuzix.bin out.img [filesystem.bin]", file=sys.stderr)
        return 2
    kernel = Path(sys.argv[1]).read_bytes()
    fs = Path(sys.argv[3]).read_bytes() if len(sys.argv) > 3 else None
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_cf(kernel, fs))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
