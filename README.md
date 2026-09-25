# ScreenAI 1.0.0

**ScreenAI** is a personal desktop assistant for **Kubuntu / KDE on X11**. You type (or speak) a
command — "open Firefox", "run ls -la", "press Ctrl+S" — and ScreenAI turns it into safe, tool-based
actions on your desktop: launching applications, running terminal commands, driving mouse/keyboard
automation, reading the screen with OCR, and executing recorded multi-step workflows. An optional
OpenAI/Ollama agent plans complex tasks through a strict tool registry — never by generating code.

> **Status:** v1.0.0 (Milestones 1–5 complete). Personal-use software; review the
> [Safety model](#11-safety-model) before enabling cloud AI.

---

## Contents

1. [What ScreenAI does](#1-what-screenai-does)
2. [Architecture overview](#2-architecture-overview)
3. [Installation](#3-installation)
4. [First-run setup](#4-first-run-setup)
5. [OpenAI setup](#5-openai-setup)
6. [Ollama setup](#6-ollama-setup)
7. [Voice setup](#7-voice-setup)
8. [X11 / Wayland limitations](#8-x11--wayland-limitations)
9. [Learn Mode](#9-learn-mode)
10. [Workflow usage](#10-workflow-usage)
11. [Safety model](#11-safety-model)
12. [Troubleshooting](#12-troubleshooting)
13. [Development instructions](#13-development-instructions)
14. [Adding a new tool](#14-adding-a-new-tool)
15. [Adding a new provider](#15-adding-a-new-provider)
16. [Adding a new plugin](#16-adding-a-new-plugin)
17. [Experimental features](#17-experimental-features)

---

## 1. What ScreenAI does

- **Command interface** on every page: text input, microphone (push-to-talk) button, current AI
  provider/model, and live task status.
- **Local command parsing** — no AI needed for common tasks: open apps, run terminal commands,
  press keys/hotkeys, type text, scroll, screenshot. Works fully offline.
- **[AI agent](#5-openai-setup) (OpenAI or Ollama)** — plans multi-step tasks by calling registered
  tools (screenshot, OCR, app list, file listing, terminal …) in a bounded loop.
- **Desktop automation** with graceful failure if `pyautogui`/X11 is unavailable.
- **Vision & OCR** — screen capture and text recognition ([experimental](#17-experimental-features)).
- **Learn Mode** — record your actions once, replay them as a workflow later.
- **Workflow Manager** — run, rename, search and delete saved workflows.
- **History** — every task with provider, duration and result; searchable and clearable.
- **System tray** — close-to-tray, pause/resume, stop current task, settings, quit.
- **Execution popup** — live task/step status with Pause, Stop, Restore and confirmation prompts.
- **Safety manager** — confirm-before-run for consequential actions, blocked destructive classes,
  an emergency Stop, and privacy modes (Local only / Allow cloud AI / Ask before cloud AI).
- **Voice input** — push-to-talk transcription ([experimental](#17-experimental-features)).
- **Plugins** — internal extension points for tools, commands, settings and UI pages.

## 2. Architecture overview

ScreenAI is deliberately modular — every subsystem is a small, swappable module with an interface:

```
core/
  version.py            # single source of truth: APP_NAME, VERSION ("1.0.0")
  config.py             # runtime-resolved paths & settings schema (no hardcoded paths)
  settings.py           # persistent settings (secrets kept out of logs)
  logging_setup.py      # central logging with secret redaction
  controller.py         # Application wiring (UI ⇄ services, signals/slots)
  agent_controller.py   # async tool-using agent loop (provider-agnostic)
  history.py            # task history service (redacted, searchable)
  diagnostics.py        # diagnostic report builder/exporter (no secrets)
  capabilities.py       # runtime capability probing (display/automation/OCR/voice/tray)
  providers/            # AIProvider interface + OpenAI / Ollama / scripting / auto
  agent/                # planner, tools loop, safety manager, confirmation queue
  tools/                # Tool interface, ToolRegistry, 16 built-in tools, safety levels
  automation/           # App/terminal control, mouse/keyboard, self-check
  vision/               # screenshot capture + OCR backends
  memory/               # SQLite workflow/session storage (no secrets)
  workflows/            # recorder, player, discovery, intent composer
  voice/                # VoiceProvider interface + push-to-talk service + backends
  plugins/              # Plugin interface, registry, per-plugin ToolRegistry, context
ui/
  main_window.py        # six-page shell: Home, AI/Chat, Learn, Workflows, History, Settings
  command_bar.py        # shared command input + mic + provider/model/status
  tray.py               # system tray (Show / Pause Agent / Stop Current Task / Settings / Quit)
  popup.py              # execution popup (task, step, status, Pause/Stop/Restore/Confirm)
  wizard.py             # 5-step first-run wizard
  settings_panel.py     # AI / Automation / Vision / Voice / Interface / Security pages
  chat_page.py / learn_page.py / workflow_page.py / history_page.py …
database/               # SQLite schema & repositories
tests/                  # pytest suite (mocked providers; no real keys/Ollama needed)
```

**Design rules** (enforced in review):

- UI never talks to backends directly — always through signals/slots and the `ApplicationController`.
- The agent loop never touches the OS directly and **never executes LLM-generated Python** —
  only registered `Tool`s (name, description, input schema, `execute()`, safety level).
- Adding a tool, provider, page, or voice engine = add a module and register it; the agent loop,
  UI shell and settings are never modified (see [14](#14-adding-a-new-tool),
  [15](#15-adding-a-new-provider), [16](#16-adding-a-new-plugin)).

## 3. Installation

### From the `.deb` package (recommended)

```bash
./build_deb.sh                       # builds dist/screenai_1.0.0_all.deb
sudo apt install ./dist/screenai_1.0.0_all.deb
screenai                             # or the application menu entry "ScreenAI"
```

Uninstall cleanly:

```bash
sudo apt remove --purge screenai
```

### Dependencies

- `python3` (≥ 3.12 on Kubuntu 24.04; the code also runs on 3.11)
- `python3-pyside6.qtwidgets`, `python3-pyside6.qtsvg` (Qt UI)
- `python3-pyautogui`, `python3-pil`, `python3-mss`, `python3-pynput` (automation/vision)
- Recommended: `xdotool` (robust app launching on KDE), `xclip` (clipboard paste)
- Optional (pip): `easyocr` (OCR), `faster-whisper` (voice) — see [17](#17-experimental-features)

### From source

```bash
python3 -m venv .venv
.venv/bin/pip install PySide6 pytest pyflakes pyautogui pillow mss
.venv/bin/python main.py
```

## 4. First-run setup

On first launch (or via **Settings → Reset first-run wizard** — *experimental*) the wizard runs
five steps:

1. **Welcome** — what ScreenAI does and where your data lives (`~/.local/share/ScreenAI`).
2. **Choose AI mode** — *Local (Ollama)*, *OpenAI*, or *Auto (prefer local)*.
3. **Configure provider** — OpenAI: API key + model (stored 0600 in `credentials.json`, shown
   masked, never logged). Ollama: host + model + **Connection test**.
4. **Desktop automation check** — X11/Wayland session, mouse, keyboard, screenshot capture, OCR.
   Unavailable pieces are disabled with a warning instead of crashing later.
5. **Privacy** — *Local only* (default, safest) / *Allow cloud AI* / *Ask before cloud AI*.

Everything the wizard writes lives in `settings.json` under the data dir and can be changed later
in Settings.

## 5. OpenAI setup

1. Settings → **AI**: provider *OpenAI*, paste your API key (e.g. `sk-…`), pick a model
   (e.g. `gpt-4o-mini`), Save.
2. **Privacy mode** must allow cloud AI — in *Local only* mode OpenAI is never called, and in
   *Ask before cloud AI* mode you are prompted first. There are **no silent provider switches**.
3. The key is loaded from settings/environment only — never hardcoded, never written to logs,
   SQLite, history, or the diagnostics export; never sent to the LLM (it is only used in the
   HTTPS `Authorization` header). A 401 shows *"API key rejected or missing"* and a retry button.

No API key? The scripting provider + local parsing handle the core commands without any AI.

## 6. Ollama setup

1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3.2`.
2. Settings → **AI**: provider *Ollama*, host (default `http://localhost:11434`), model name,
   **Test connection**.
3. Ollama is **local** — it is used in every privacy mode and is preferred by *Auto* mode.
4. If Ollama is down: clear error *"Ollama is not available at http://localhost:11434."* and
   suggestions (start Ollama / switch provider). No crashes, no infinite retries.

## 7. Voice setup

1. Install a transcription engine ([experimental](#17-experimental-features)): `pip install faster-whisper`.
2. Settings → **Voice**: provider (or *None (typed input only)*), microphone, and push-to-talk.
3. Press the 🎤 button (hold for push-to-talk): the recording is transcribed and placed **into the
   command box as editable text** — nothing executes until you press Run.
4. Microphone errors (permission, device missing, engine missing) show a clear message; with
   *None* selected or no engine installed, everything else in ScreenAI still works normally.

New engines implement `core.voice.VoiceProvider` and register — see [15](#15-adding-a-new-provider).

## 8. X11 / Wayland limitations

| Capability | X11 (target) | Wayland |
|---|---|---|
| Screenshots (`mss`) | ✅ | ❌ usually blocked |
| Mouse/keyboard control | ✅ | ❌ (`pyautogui` fails; GRAB_ERROR) |
| Global emergency Stop (pynput) | ✅ | ⚠️ limited |
| App launching / terminal | ✅ | ✅ (xdotool paths degrade) |
| Typing via clipboard (`xdotool type` / `Ctrl+V`) | ✅ | ⚠️ needs portal-based clipboard |
| OCR on captured frames | ✅ | ❌ (depends on screenshots) |

ScreenAI **fails gracefully** on Wayland: the wizard's automation check reports each unavailable
capability with a warning, and affected tools return actionable errors instead of crashing.
**KDE on X11 is the supported target** (Kubuntu). On Wayland, app launching, terminal control,
workflows that only use those, chat and history all still work.

## 9. Learn Mode

1. Open **Learn** in the sidebar (learning is **always explicit** — ScreenAI never records
   normal interactions as workflows).
2. Click **Record** and perform the actions: mouse moves/clicks, typing, key presses, app launches.
3. **Stop** and name the workflow ("My report flow"). Steps are stored in SQLite with their delays.

Learn Mode shows Recording/Playing/idle status with Stop always available.

## 10. Workflow usage

The **Workflows** page lists every saved workflow: application, workflow name, step count and
creation date. You can **search**, **run**, **rename** and **delete** workflows, or jump back to
Learn Mode. Running a workflow plays its steps in order with per-step status in the execution
popup; **Stop** cancels playback mid-run. If a workflow's target application is missing, you get
*"Workflow target app not found."* — the app never crashes.

Workflows can also be executed by the agent through the `workflow_play` tool (subject to
confirmation policy), and simple intents like "open Firefox" can be auto-composed from a natural
command through the intent planner.

## 11. Safety model

- **Tool-only execution.** The LLM plans; only registered tools act. Arbitrary LLM-generated
  Python is **never executed**; the prompt explicitly forbids code output and stray code is ignored.
- **Safety levels** on every tool: `SAFE` (run), `CONFIRM` (ask first), `CONSEQUENTIAL` (ask first),
  `BLOCKED` (refused). Terminal commands, file deletion, sending messages, purchases, form
  submission and external-account actions require confirmation. Destructive disk operations,
  credential extraction, disabling security and privilege escalation are blocked by policy.
- **Confirmation policy** (Settings → Security): `required_only` (default) / `always` / `never`
  / `blocked`. The confirmation prompt shows the exact command/action with **Confirm** and
  **Cancel**; the agent pauses until you decide.
- **Emergency Stop** (popup, tray, global shortcut) cancels the agent loop, automation, workflow
  playback and cancellable terminal processes immediately.
- **Pause / Resume** (popup + tray): pause stops starting new actions, lets the current safe
  operation finish and preserves agent state; resume continues where it stopped.
- **Privacy modes.** *Local only* (default): screenshots and commands never leave the machine.
  *Allow cloud AI*: OpenAI may receive command text and screenshots as tool output. *Ask before
  cloud AI*: prompted per session. No silent provider switches.
- **Secrets.** API keys/tokens/passwords are never logged (a `redact()` filter backs this),
  never stored in SQLite, never shown in full after save, and never included in diagnostics
  exports or history. Stored credentials live in a 0600 `credentials.json` and can be wiped from
  Settings → Security ("Clear stored credentials").
- **Screenshots** are in-memory frames only; permanent screenshot history is off unless you
  enable it explicitly (Settings → Vision).

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| "API key rejected or missing" | Re-enter the key in Settings → AI; check the model name. |
| "Ollama is not available…" | `ollama serve`; check host/port; press **Test connection**. |
| "Screen capture failed…" | Use an X11 session; give no extra permissions — `mss` needs none on X11. |
| "Screenshot / automation unavailable (Wayland?)` | See [§8](#8-x11--wayland-limitations); use X11. |
| "OCR unavailable" | `pip install easyocr` (downloads a model on first use). |
| "Application not found" | Install the app or use its exact desktop name; `xdotool` recommended. |
| "Workflow target app not found." | The recorded app is missing; open it or edit the workflow. |
| "Microphone permission denied" / no mic | System Settings → Audio → Input; or set Voice provider to None. |
| "Voice provider unavailable" | `pip install faster-whisper`, or pick None — typing still works. |
| Popup seems stuck | It never blocks input — use **Stop**; check History for the failure reason. |
| Suspicion of a secret leak | Settings → Security → Clear stored credentials; `redact()` also strips `sk-…` keys from all logs and history. |

Diagnostics: **Settings → Security → Export diagnostic report** writes a text file with version,
Python/Qt/OS info, provider *type* (never secrets), capabilities and recent error categories —
it contains **no API keys, passwords, tokens or cookies** (automated test: `tests/test_m5_diagnostics.py`).

## 13. Development instructions

```bash
git clone https://github.com/hp635738-pro/ScreenAI.git
cd ScreenAI
python3 -m venv .venv
.venv/bin/pip install PySide6==6.11.1 pytest pyflakes pyautogui pillow mss pynput

# tests (mocked providers; no real API key or Ollama needed)
.venv/bin/python -m pytest tests/ -q

# lint + syntax gate
.venv/bin/python -m pyflakes main.py core ui database tests examples
.venv/bin/python -m compileall -q main.py core ui database tests examples

# run
.venv/bin/python main.py
```

- Architecture and design rules: [§2](#2-architecture-overview). Keep UI and business logic
  separate; use signals/slots; resolve paths at runtime (`core.config.Config`).
- Tests use fakes (`tests/fakes.py`): `ScriptedProvider`, `FakeBackend`, `FakeAudioRecorder` …
- Milestone build notes: `docs/milestone2-plan.md` … `docs/milestone5-final-release-plan.md`.

## 14. Adding a new tool

A tool is one class. The agent loop, registry and UI never change.

```python
from core.tools import Tool, ToolResult, ToolSpec
from core.tools.safety import SafetyLevel

class WeatherTool(Tool):
    def __init__(self):
        super().__init__()
        self.spec = ToolSpec(
            name="weather_lookup",              # unique name
            description="Look up current weather for a city.",
            input_schema={                       # JSON schema the LLM sees
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            safety=SafetyLevel.SAFE,             # SAFE / CONFIRM / CONSEQUENTIAL / BLOCKED
        )

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(success=True, output="22°C, clear")
```

Register it — one line, nothing else:

```python
registry.register(WeatherTool())           # core/agent_controller.py build step,
                                           # or a plugin (see §16)
```

That's the whole process used by all 16 built-in tools (`core/tools/*`) — each is independently
testable with its own name, description, schema, safety classification and `execute()`.

## 15. Adding a new provider

Implement `core.providers.base.AIProvider` — three methods, no UI knowledge required:

```python
from core.providers.base import AIProvider, ProviderNotConfigured

class MyProvider(AIProvider):
    def __init__(self, model: str, **kwargs):
        super().__init__(name="my-provider", is_cloud=True, model=model)

    def is_available(self) -> bool:
        return True                       # report configuration state honestly

    def generate(self, prompt: str, *, context=None) -> str:
        ...

    def chat(self, messages, *, stream_cb=None) -> str:
        ...
```

Then expose it in `core/providers/factory.py` (one entry in the provider map + settings keys).
The settings UI, wizard, agent, history labels and diagnostics pick it up automatically.
The same pattern applies to **voice engines** (`core.voice.VoiceProvider`: `record()` +
`transcribe()` — see `core/voice/whisper_provider.py`) and **automation backends** /
**vision backends** (small interfaces in their packages).

## 16. Adding a new plugin

Plugins are an **internal extension architecture** (there is no marketplace). A plugin can
register **tools**, **commands**, **settings**, and an optional **UI page** — without modifying
the core agent.

```python
from core.plugins import Plugin, PluginContext, Command, SettingDef, UIPage

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__(name="my-plugin", version="1.0.0", description="…")

    def on_load(self, context: PluginContext) -> None:
        context.register_tool(MyTool())                    # Tool instance (§14)
        context.register_command(Command("my_cmd", "Run thing", lambda: "done"))
        context.register_setting(SettingDef("my.key", "My option", "default"))
        context.register_page(UIPage("My Page", widget_factory=make_widget))  # optional

PLUGIN_CLASS = MyPlugin
```

Drop the file into `~/.local/share/ScreenAI/plugins/` — ScreenAI loads it at startup
(never from this repository's tree automatically). See
[`examples/photoshop_plugin.py`](examples/photoshop_plugin.py) for a full example: a
Photoshop bridge registering three Photoshop tools, a command, a setting and a UI page
**without touching the core agent**. Plugin load errors are collected and reported in the
diagnostics export; a broken plugin never crashes the app.

## 17. Experimental features

These work but are marked **experimental** — APIs may change and they need optional pip
dependencies:

- **Voice transcription** (push-to-talk → text): needs `faster-whisper`; the interface
  (`VoiceProvider`) is stable. Without it, typed input is fully supported.
- **OCR** (EasyOCR): needs `pip install easyocr` (large first-run model download).
- **Plugins / example plugin**: the internal plugin API (`core.plugins`) is usable but young;
  `examples/photoshop_plugin.py` is documentation-grade and ships **not** auto-loaded.
- **First-run wizard reset** (Settings → Interface) re-runs the wizard — handy for re-probing
  capabilities after fixing permissions.
- **Auto-composer** (natural intent → workflow draft) suggests drafts; it never auto-saves a
  workflow without you.

---

MIT-style personal project. Report issues at the project repository.
