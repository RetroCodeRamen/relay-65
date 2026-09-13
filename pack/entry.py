"""PyInstaller entry. The spec puts emulator/ on sys.path."""

from relay65.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
