# Repository Guidelines

## Project Structure & Module Organization
This repository is mostly flat. Core entry points live in the root:
- `venus_gui.py`: PyQt6 GUI for configuring the mouse.
- `venus_protocol.py`: Protocol implementation and device I/O helpers.
- `NEW_PROTOCOL.md`, `PROTOCOL.md`, `MACRO_ANALYSIS.md`, `win.md`: protocol notes and research.
- Analysis and experiments use filename prefixes like `analyze_*.py`, `debug_*.py`, `test_*.py`.
- Captures and artifacts are stored in `dumps/`, `usbcap/`, and `UtechSmart/`.

Keep new scripts in the root with the same naming patterns and put binary captures in `dumps/` or `usbcap/`.

## Build, Test, and Development Commands
There is no build step. Typical local setup:
- `pip install cython hidapi PyQt6` installs runtime dependencies.
- `python3 venus_gui.py` launches the GUI.

If you need non-root access to the device, follow the udev rule example in `README.md`.

## Coding Style & Naming Conventions
- Python uses 4-space indentation and `snake_case` for functions/variables.
- Keep modules small and script-oriented; this repo favors standalone scripts.
- Prefer explicit names that align with existing patterns (`analyze_*`, `test_*`, `debug_*`).

## Testing Guidelines
There is no unified test runner. Validation is done via targeted scripts:
- Run a specific script with `python3 test_macro_verify.py` (or another `test_*.py`).
- Many tests and debug scripts require a connected Venus Pro in wired mode.
- If a script writes to the device, call that out in your PR summary.

## Commit & Pull Request Guidelines
Recent history uses short, imperative subjects, sometimes with prefixes like `feat:` or `docs:`.
- Keep commits focused and describe the intent in the first line.
- PRs should include a concise summary, test steps (or “not run”), and hardware context.
- Attach new captures or protocol notes when behavior changes.

## Security & Configuration Tips
Avoid running configuration scripts against an untrusted USB device. When adding new tooling, prefer explicit device IDs and document any safety assumptions in `README.md`.
