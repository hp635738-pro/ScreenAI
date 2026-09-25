# ScreenAI

Dark, modern Linux desktop assistant and **control engine** for Kubuntu (Qt/KDE).

**Milestone 2** turns ScreenAI into a real desktop control engine: natural commands are parsed locally into structured actions, then executed — launching installed apps, running terminal commands, and driving mouse/keyboard automation — while a frameless always-on-top popup tracks progress step by step. AI backends (OpenAI, Ollama) remain stubbed for a later milestone.

## Features

### Milestone 1 — framework and floating popup
- Dark modern UI (Fusion + custom QSS theme in `assets/qss/dark.qss`)
- Main window with command input, **Run**, **Voice** (placeholder), live status indicator
- On **Run**: the main window minimizes and a frameless always-on-top **execution popup** appears (draggable, `×`/`Esc` to dismiss)
- **Restore** reopens the main window; nothing ever blocks the GUI thread
- Provider framework ready for OpenAI and Ollama (`core/providers/`)

### Milestone 2 — control engine
- **Application launcher** (`core/app_launcher.py`) — natural aliases (`firefox`, `chrome`, `brave`, `vscode`, `konsole`, `dolphin`, `settings`, `terminal`, `files`, `kate`) resolved on `PATH` at runtime and launched with `subprocess.Popen` (no shell)
- **Terminal engine** (`core/terminal.py`) — `execute(command)` with streamed stdout/stderr via Qt signals, full capture, exit code; explicit `sh -c` only for pipelines/redirections; runs off the GUI thread
- **Automation layer** (`core/automation.py`) — mouse move, left/right click, double click, typing, hotkeys — `pyautogui` primary, `xdotool` fallback
- **Intent parser** (`core/intent_parser.py`) — lightweight local (no AI) command→action parsing with multi-step chains
- **Popup step progress** — `Working… / Step 1/3 / Opening Firefox` updated live through signals, plus streamed terminal output line
- **Action history** — every executed step stored in SQLite (`timestamp`, `command`, `action`, `success`, `duration`) alongside the run history
- **Emergency stop** — global **Stop** (main window *and* popup) immediately and safely cancels running automation: typing aborts between chunks, terminal process groups get SIGTERM→SIGKILL, remaining steps are skipped

## Command examples

| Say | Do |
| --- | --- |
| `open firefox` / `launch vscode` / `open terminal` | Launch an installed app (aliases resolve to real executables) |
| `run ls -la` / `run in terminal echo hi` | Execute in the terminal engine (streamed, captured) |
| `type hello world` | Type text (quote it to include `then`/`;`) |
| `press ctrl+c` / `hotkey ctrl shift t` | Press hotkeys / single keys (`enter`, `tab`, …) |
| `move mouse to 100 200` | Move the mouse |
| `click at 300 400` / `right click` / `double click at 10 20` | Click |
| `wait 2s` | Pause between steps |
| `open firefox then type hello world` | Chain steps (`then`, `and then`, `;`) |
| `simulate writing a report` | Milestone 1 simulated run (no AI yet) |

Anything unrecognized is rejected politely and logged to the action history.

## Requirements

- Kubuntu (or any Qt/KDE Linux desktop). Automation needs X11 or XWayland (`pyautogui`/`xdotool` are X11-bound; Wayland-native input injection is a later milestone)
- Python 3.12+
- `PySide6`, `pyautogui` (see `requirements.txt`), optional `xdotool` as automation fallback

## Launch instructions

### From source

```bash
cd ScreenAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### As a .deb package

```bash
cd ScreenAI
./build_deb.sh
sudo apt install ./dist/screenai_0.1.0_all.deb
screenai
```

The package installs app code to `/usr/lib/screenai`, a launcher at `/usr/bin/screenai`, a desktop entry and icon. Declared dependencies: `python3-pyside6.qtwidgets`, `python3-pyside6.qtsvg`, `python3-pyautogui`; `xdotool` is recommended. With pip-managed PySide6 install the .deb via `dpkg -i --force-depends` or adjust `build_deb.sh`.

Environment variables:

| Variable | Effect |
| --- | --- |
| `SCREENAI_DATA_DIR` | Override the data directory (database location). Defaults to `~/.local/share/ScreenAI` via `QStandardPaths`. |

## Project structure

```
ScreenAI/
├── main.py               # Entry point: QApplication bootstrap
├── requirements.txt      # Runtime dependencies
├── build_deb.sh          # .deb packaging script
├── assets/
│   ├── icons/            # App + button icons (SVG)
│   └── qss/              # dark.qss — full application theme
├── core/                 # Business logic (UI-free)
│   ├── config.py         # App config + runtime path resolution
│   ├── controller.py     # Wires UI ↔ engines via signals/slots
│   ├── models.py         # TaskState, Plan, Action, results, records
│   ├── intent_parser.py  # Local command → Plan parser (no AI)
│   ├── app_launcher.py   # Alias-based app launcher (Popen)
│   ├── terminal.py       # Terminal engine (streamed, cancellable)
│   ├── automation.py     # pyautogui/xdotool input automation
│   ├── plan_executor.py  # QThread plan runner + emergency stop
│   ├── task_manager.py   # Milestone 1 simulation lifecycle
│   ├── task_worker.py    # Simulated worker
│   ├── voice_service.py  # Voice placeholder service
│   └── providers/        # AI backends (stubs, untouched)
├── database/             # SQLite persistence
│   ├── db_manager.py     # Connection + schema bootstrap
│   ├── schema.sql        # task_runs + action_history
│   ├── task_repository.py
│   └── action_repository.py
└── ui/                   # Qt widgets (no business logic)
    ├── main_window.py    # Input, Run/Stop/Voice, status
    ├── popup.py          # Execution popup (steps, live output)
    ├── theme.py          # Palette + QSS loader
    └── widgets.py        # StatusIndicator, StatusDot, HintLabel
```

## Architecture notes

- **UI / logic separation** — widgets expose signals and dumb setters; `core/` never imports widgets except `controller.py`, the single composition point.
- **Signals/slots everywhere** — worker threads → controller → windows (`step_started`, `step_finished`, `output_line`, `plan_completed`); cross-thread delivery stays queued, so the UI never freezes.
- **Execution model** — `PlanExecutor` owns one `QThread` + `PlanWorker` per plan (standard `quit`/`deleteLater` teardown). Failures abort remaining steps; `emergency_stop()` is safe from any thread.
- **Terminal safety** — commands run without a shell unless they contain shell metacharacters (then explicit `sh -c`); the process runs in its own session and is killed by process group on cancel.
- **Automation safety** — `pyautogui.FAILSAFE` (mouse-corner abort), cooperative abort checks between typing chunks, `xdotool` fallback behind the same `InputBackend` interface.
- **No hardcoded paths** — assets resolve from the project root; databases live in `QStandardPaths.AppLocalDataLocation` (overridable via `SCREENAI_DATA_DIR`).
- **Providers untouched** — `core.providers.create_provider("openai" | "ollama")` stays the AI integration point for a later milestone.

## Roadmap

- **Milestone 3** — AI providers (Ollama first, then OpenAI) mapping natural language to plans; real Pause/Resume; voice input capture.
- Later — screen context capture (vision), history UI, Wayland-native automation.
