# ScreenAI

Dark, modern Linux desktop assistant and **control engine** for Kubuntu (Qt/KDE).

**Milestone 3** gives ScreenAI visual understanding and the ability to learn: the desktop is captured continuously (`mss` + Pillow), text on screen is read offline (EasyOCR), and **Learn Mode** records your clicks, hotkeys and typed text as replayable workflows — played back OCR-first with coordinate fallback. The Milestone 2 control engine (local command parsing, app/terminal/automation execution, always-on-top popup) is unchanged. AI backends (OpenAI, Ollama) remain stubbed for a later milestone.

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

### Milestone 3 — vision and learn mode
- **Vision engine** (`core/vision.py`) — continuous desktop capture with `mss` + Pillow refreshed every 300–500 ms; per-monitor and active-window-only modes; every frame is delivered as **both QImage and PIL image** through queued signals
- **OCR engine** (`core/ocr.py`) — EasyOCR text detection (`detect_text(image)`, `find_text("Export")`) returning bounding boxes and confidences; fully offline once models are cached
- **Learn Mode recorder** (`core/learn_mode.py`) — records mouse clicks, keyboard shortcuts, typed text (coalesced into sentences), window title and timestamps while you demonstrate a task; clicks are labeled with the OCR text near the cursor (`Click File`) and double-clicks are merged automatically
- **Workflow storage** — SQLite tables `workflows` (app_name, task_name, created_at) and `workflow_steps` (action, target_text, coordinates, delay, metadata JSON)
- **Workflow player** (`core/workflow_player.py`) — replays saved workflows on a worker thread; clicks prefer OCR text (`Found Export`) and fall back to saved coordinates; each step is retried twice before failing; live progress (`Playing… / Found Export / Step 6/9`)
- **Learn page** — `Start Recording`, `Stop`, `Save Workflow` with App Name / Task Name fields, live screen preview with capture-mode picker, and a saved-workflow list (double-click to play)

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

## Learn Mode

1. Open the **Learn** page and pick a capture mode (all monitors / active window / single monitor); the preview refreshes live.
2. Fill **App Name** and **Task Name**, press **Start Recording**, then perform the task once (the main window minimizes; the popup shows `Recording… / Click File / Step 4`).
3. Press **Stop**, review the recorded steps, then **Save Workflow**.
4. Double-click a saved workflow (or select it and press **Play**) to replay it. Global **Stop** cancels playback or recording at any time.


## Requirements

- Kubuntu (or any Qt/KDE Linux desktop). Automation needs X11 or XWayland (`pyautogui`/`xdotool` are X11-bound; Wayland-native input injection is a later milestone)
- Python 3.12+
- `PySide6`, `pyautogui`, `mss`, `Pillow`, `easyocr`, `pynput` (see `requirements.txt`), optional `xdotool` as automation fallback
- **Offline by design** — OCR and learn/play run locally; no API keys and no OpenAI/Ollama calls in this milestone. EasyOCR + torch install from pip; the first OCR use caches models locally.
- `pynput` may pull `evdev`, which needs `python3-dev` to build. In minimal environments install it with `pip install pynput --no-deps && pip install python-xlib six`.

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

The package installs app code to `/usr/lib/screenai`, a launcher at `/usr/bin/screenai`, a desktop entry and icon. Declared dependencies: `python3-pyside6.qtwidgets`, `python3-pyside6.qtsvg`, `python3-pyautogui`, `python3-pil`, `python3-mss`, `python3-pynput`; `xdotool` is recommended. `easyocr` is pip-only — install it in a venv (or `pip install easyocr`) for OCR/learn features. With pip-managed PySide6 install the .deb via `dpkg -i --force-depends` or adjust `build_deb.sh`.

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
│   ├── vision.py         # mss/Pillow capture: QImage + PIL frames, multi-monitor
│   ├── ocr.py            # EasyOCR text detection + find_text (offline)
│   ├── learn_mode.py     # WorkflowRecorder: clicks/keys/typing → steps
│   ├── workflow_player.py# OCR-first workflow replay + retries + progress
│   ├── task_manager.py   # Milestone 1 simulation lifecycle
│   ├── task_worker.py    # Simulated worker
│   ├── voice_service.py  # Voice placeholder service
│   └── providers/        # AI backends (stubs, untouched)
├── database/             # SQLite persistence
│   ├── db_manager.py     # Connection + schema bootstrap
│   ├── schema.sql        # task_runs, action_history, workflows, workflow_steps
│   ├── task_repository.py
│   ├── action_repository.py
│   └── workflow_repository.py
└── ui/                   # Qt widgets (no business logic)
    ├── main_window.py    # Command + Learn pages, nav, status
    ├── learn_page.py     # Learn page (record/save/play workflows, preview)
    ├── popup.py          # Execution popup (steps, recording/playback)
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
- **Learn pipeline** — `pynput` listeners (lazy, so headless import is safe) feed `WorkflowRecorder`, which coalesces raw events into `LearnedStep`s (typing runs, double-click merge, `Ctrl+S`-style hotkeys). The player replays in a `QThread` with OCR-first targeting, saved-coordinate fallback and bounded retries; recording and playback are stoppable from any thread.
- **Providers untouched** — `core.providers.create_provider("openai" | "ollama")` stays the AI integration point for a later milestone.

## Roadmap

- **Milestone 4** — AI providers (Ollama first, then OpenAI) mapping natural language to plans; real Pause/Resume; voice input capture.
- Later — history UI, Wayland-native automation, workflow editing.
