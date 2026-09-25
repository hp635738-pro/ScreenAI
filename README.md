# ScreenAI

Dark, modern Linux desktop assistant for Kubuntu (Qt/KDE). **Milestone 1** delivers the application framework and a floating execution popup: type a command, run it, and watch progress from a frameless always-on-top HUD while the main window minimizes. AI backends (OpenAI, Ollama) are stubbed and land in a later milestone — executions in this milestone are simulated in a background thread.

## Features (Milestone 1)

- Dark modern UI (Fusion + custom QSS theme in `assets/qss/dark.qss`)
- Main window with command input, **Run** button, **Voice** button (placeholder) and live status indicator (Ready / Working / Done / Error)
- On **Run**:
  - the main window minimizes automatically
  - a frameless, always-on-top **execution popup** appears showing the current task, status (Working/Done), and **Pause** / **Stop** buttons (UI-only placeholders) plus **Restore**
- Popup stays fully responsive — execution runs in a `QThread` worker and communicates via signals/slots (never blocks the GUI thread)
- **Restore** button reopens (un-minimizes) the main window
- Popup is draggable, dismissible (`×` or `Esc`)
- Task runs are recorded to a local SQLite database (`~/.local/share/ScreenAI/screenai.db` by default)
- Provider framework ready for OpenAI and Ollama (`core/providers/`)

Scope notes (deliberate for Milestone 1):

- **Pause** and **Stop** are UI-only placeholders — no task control yet.
- **Voice** is a UI-only placeholder — no audio capture yet.
- No AI is called; the worker simulates a ~5 s execution (configurable via `Config.TASK_SIM_DURATION`).

## Requirements

- Kubuntu (or any Qt/KDE Linux desktop), X11 or Wayland
- Python 3.12+
- PySide6 (`requirements.txt`, or the distro packages `python3-pyside6.qtwidgets` + `python3-pyside6.qtsvg`)

## Launch instructions

### From source (recommended during development)

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

The build script stages a classic `Architecture: all` package: app code in `/usr/lib/screenai`, launcher at `/usr/bin/screenai`, desktop entry and icon in `/usr/share/...`. The declared dependencies are `python3 (>= 3.12)`, `python3-pyside6.qtwidgets`, `python3-pyside6.qtsvg` (available in Ubuntu 24.04+). If you prefer pip-installed PySide6, install the .deb with `dpkg -i --force-depends` or adjust the `Depends:` line in `build_deb.sh`.

## Usage

1. Start ScreenAI — the main window opens with status **Ready**.
2. Type a command (e.g. `Summarize the text on screen`) and press **Run** (or Enter).
3. The main window minimizes; the floating popup shows the task, pulsing **Working** status and progress hints.
4. Press **Restore** to bring the main window back at any time (the popup keeps tracking the task; drag it anywhere).
5. When the simulated run completes the popup switches to **Done**. Dismiss it with **×** or **Esc**.

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
│   ├── controller.py     # Wires UI ↔ services via signals/slots
│   ├── models.py         # TaskState, TaskRecord
│   ├── task_manager.py   # Task lifecycle (owns the QThread)
│   ├── task_worker.py    # Background worker (simulated run for now)
│   ├── voice_service.py  # Voice placeholder service
│   └── providers/        # AI backends (stubs)
│       ├── base.py             # AIProvider contract + errors
│       ├── openai_provider.py  # OpenAI stub
│       └── ollama_provider.py  # Ollama stub
├── database/             # SQLite persistence
│   ├── db_manager.py     # Connection + schema bootstrap
│   ├── schema.sql        # task run history
│   └── task_repository.py
└── ui/                   # Qt widgets (no business logic)
    ├── main_window.py    # Command input, Run/Voice, status
    ├── popup.py          # Frameless always-on-top execution popup
    ├── theme.py          # Palette + QSS loader
    └── widgets.py        # StatusIndicator, StatusDot, HintLabel
```

## Architecture notes

- **UI / logic separation** — `ui/` widgets expose signals (`run_requested`, `restore_requested`, …) and dumb setters; `core/` never imports widgets except in `controller.py`, the single composition point.
- **Signals/slots everywhere** — worker → manager → controller → windows; cross-thread delivery is queued automatically so the UI never freezes.
- **Thread model** — `TaskManager` owns a `QThread` + `TaskWorker` per run with the standard `quit`/`deleteLater` teardown. `TaskWorker.request_stop()` is the hook real cancellation will use.
- **No hardcoded paths** — assets resolve from the project root; the database lives in `QStandardPaths.AppLocalDataLocation` (overridable via `SCREENAI_DATA_DIR`), so the app works both from a checkout and from `/usr/lib/screenai`.
- **Providers** — `core.providers.create_provider("openai" | "ollama")` returns an `AIProvider` implementing `is_available()` / `generate()`. Milestone 1 keeps them as stubs; `Config.AI_PROVIDER_OPTIONS` reserves their settings.

## Roadmap

- **Milestone 2** — real provider integrations (Ollama first, then OpenAI), streamed responses into the popup.
- **Milestone 3** — functional Pause/Stop (worker already supports cooperative cancellation), voice input capture/transcription.
- Later — screen context capture, history UI over `task_runs`, packaging polish.
