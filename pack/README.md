# Frozen desktop apps

Windows and Linux binaries for **[Relay-65 v1.0.0](https://github.com/RetroCodeRamen/relay-65/releases/tag/v1.0.0)**.

A downloader does not need Python, cc65, or Contiki. Double-click the app: Clack loads from `software/images/console.bin`, warp clock, RUN. The front panel is the same layout as `./relay65 --gui` (tkinter window, or the browser UI at `http://127.0.0.1:8065` if tkinter is not in the freeze).

## What GitHub Actions builds

`.github/workflows/package.yml` on a `v*` tag (and on **Actions → Package → Run workflow**):

| Artifact | File on the release |
| --- | --- |
| `Relay-65-windows` | `Relay-65-windows.exe` |
| `Relay-65-linux` | `Relay-65-linux` |

The tag job attaches those files to the GitHub release. `workflow_dispatch` only uploads Actions artifacts (no release).

## Rebuild locally

Needs `software/images/console.bin` (copied by `make -C software/contiki`).

```bash
pip install pyinstaller
pyinstaller pack/relay65.spec
# dist/Relay-65       (Linux)
# dist/Relay-65.exe   (Windows — build on Windows)
```

Linux freeze should use a Python that can `import tkinter` (Debian/Ubuntu: `python3-tk`) so the desktop window is bundled. Without tkinter the app still runs and opens the browser panel.

Windows freeze needs the python.org installer (tkinter included). `--panel` is not for Windows.

The spec packs:

- `emulator/rom/monitor.s` → assembled at start
- `software/images/console.bin` → loaded at `$0200`

Frozen defaults (no flags): `--gui --overclock --run --load images/console.bin`.
