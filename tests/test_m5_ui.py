"""Milestone 5: tray, wizard, history/workflow pages, main-window sections."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from core.safety import SafetyManager
from core.settings import SettingsStore
from core.version import APP_NAME, VERSION
from ui.history_page import HistoryPage
from ui.main_window import MainWindow
from ui.tray import AppTray
from ui.wizard import FirstRunWizard
from ui.workflow_page import WorkflowPage
from core.models import WorkflowSummary
from core.history import HistoryEntry


# ------------------------------------------------------------------ tray

def test_tray_menu_items(qapp) -> None:  # noqa: ANN001, ANN202
    tray = AppTray()
    labels = [
        tray.action_show.text(),
        tray.action_pause.text(),
        tray.action_stop.text(),
        tray.action_settings.text(),
        tray.action_quit.text(),
    ]
    assert labels == [
        "Show ScreenAI",
        "Pause Agent",
        "Stop Current Task",
        "Settings",
        "Quit ScreenAI",
    ]
    tray.set_paused(True)
    assert tray.action_pause.text() == "Resume Agent"
    tray.set_paused(False)
    assert tray.action_pause.text() == "Pause Agent"
    tray.hide()


# ----------------------------------------------------------------- wizard

def test_wizard_five_steps_and_safest_defaults(qapp) -> None:  # noqa: ANN001, ANN202
    settings = SettingsStore()
    wizard = FirstRunWizard(settings, SafetyManager())
    assert wizard._stack.count() == 5
    assert not wizard._next.isHidden()
    # AI mode default: Auto (index 2); privacy default: Local only (index 0).
    wizard._show_page(1)
    assert wizard._mode_group.checkedId() == 2
    wizard._show_page(4)
    assert wizard._privacy_group.checkedId() == 0
    assert not wizard._finish.isHidden()


def test_wizard_apply_settings_writes_store(qapp) -> None:  # noqa: ANN001, ANN202
    settings = SettingsStore()
    wizard = FirstRunWizard(settings, SafetyManager())
    values = wizard.apply_settings()
    assert values["first_run_done"] is True
    assert values["provider"] == "auto"
    assert values["privacy"] == "local_only"
    assert settings.get("first_run_done") is True
    assert settings.get("privacy") == "local_only"


def test_wizard_provider_page_has_ollama_test(qapp) -> None:  # noqa: ANN001, ANN202
    wizard = FirstRunWizard(SettingsStore(), SafetyManager())
    wizard._show_page(2)
    assert wizard._test_button.text() == "Test connection"
    assert wizard._api_key.echoMode().name == "Password"


# ------------------------------------------------------------- main window

def test_main_window_has_six_sections(qapp) -> None:  # noqa: ANN001, ANN202
    window = MainWindow(SettingsStore())
    assert window._stack.count() == 6
    assert window.PAGE_HOME == 0
    assert window.PAGE_LEARN == 2
    assert window.PAGE_HISTORY == 4
    assert window.PAGE_SETTINGS == 5
    assert set(window._nav_buttons) == set(range(6))
    assert window.windowTitle().startswith(APP_NAME)
    assert VERSION in window.windowTitle()


def test_main_window_close_to_tray_hides(qapp) -> None:  # noqa: ANN001, ANN202
    window = MainWindow(SettingsStore())
    hidden: list[bool] = []
    window.hidden_to_tray.connect(lambda: hidden.append(True))
    window.set_close_to_tray(True)
    window.close()
    assert window.isVisible() is False
    assert hidden == [True]


def test_main_window_close_quits_when_tray_disabled(qapp) -> None:  # noqa: ANN001, ANN202
    window = MainWindow(SettingsStore())
    quits: list[bool] = []
    window.force_quit = lambda: quits.append(True)
    window.set_close_to_tray(False)
    window.close()
    assert quits == [True]


def test_command_interface_widgets(qapp) -> None:  # noqa: ANN001, ANN202
    window = MainWindow(SettingsStore())
    window.set_provider_status("Provider: auto · llama3.2")
    assert "auto" in window._provider_label.text()
    window.set_command_text("open firefox")
    assert window.command() == "open firefox"
    states: list[str] = []
    window.run_requested.connect(states.append)
    window._emit_run()
    assert states == ["open firefox"]


# ---------------------------------------------------------------- history

def test_history_page_filters_and_clear(qapp) -> None:  # noqa: ANN001, ANN202
    page = HistoryPage()
    page.set_entries(
        [
            HistoryEntry("2026-09-26T10:00:00", "open firefox", "ollama", 1.2, "ok", True, "agent"),
            HistoryEntry("2026-09-26T10:01:00", "send mail", "openai", 0.4, "failed", False, "agent"),
        ]
    )
    assert page._table.topLevelItemCount() == 2
    emitted: list[tuple[str, str]] = []
    page.filter_requested.connect(lambda s, f: emitted.append((s, f)))
    page._search.setText("firefox")
    assert emitted and emitted[-1][0] == "firefox"


def test_history_page_clear_requires_confirmation(qapp, monkeypatch) -> None:  # noqa: ANN001, ANN202
    page = HistoryPage()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    cleared: list[int] = []
    page.clear_requested.connect(lambda: cleared.append(1))
    page._confirm_clear()
    assert cleared == []  # declined


# --------------------------------------------------------------- workflows

def test_workflow_page_lists_and_searches(qapp) -> None:  # noqa: ANN001, ANN202
    page = WorkflowPage()
    page.set_workflows(
        [WorkflowSummary(
            id=1,
            app_name="Firefox",
            task_name="Export report",
            step_count=4,
            created_at="2026-09-26",
        )]
    )
    assert page._table.topLevelItemCount() == 1
    assert page._table.topLevelItem(0).text(0) == "Firefox"
    searches: list[str] = []
    page.search_changed.connect(searches.append)
    page._search.setText("export")
    assert searches == ["export"]


def test_workflow_page_delete_confirmation(qapp, monkeypatch) -> None:  # noqa: ANN001, ANN202
    from PySide6.QtCore import Qt

    page = WorkflowPage()
    page.set_workflows(
        [WorkflowSummary(
            id=1,
            app_name="Firefox",
            task_name="Export report",
            step_count=4,
            created_at="2026-09-26",
        )]
    )
    item = page._table.topLevelItem(0)
    page._table.setCurrentItem(item)
    assert page.selected_id() == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    deleted: list[int] = []
    page.delete_requested.connect(deleted.append)
    page._emit_delete()
    assert deleted == [1]
    # run signal
    runs: list[int] = []
    page.run_requested.connect(runs.append)
    page._emit_run()
    assert runs == [1]
    del Qt


def test_workflow_rename_flow(qapp, monkeypatch) -> None:  # noqa: ANN001, ANN202
    from PySide6.QtWidgets import QInputDialog

    page = WorkflowPage()
    page.set_workflows(
        [WorkflowSummary(
            id=1,
            app_name="Firefox",
            task_name="Export report",
            step_count=4,
            created_at="2026-09-26",
        )]
    )
    page._table.setCurrentItem(page._table.topLevelItem(0))
    answers = iter([("Firefox", True), ("Report v2", True)])
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: next(answers)
    )
    renamed: list[tuple[int, str, str]] = []
    page.rename_requested.connect(lambda *args: renamed.append(args))
    page._emit_rename()
    assert renamed == [(1, "Firefox", "Report v2")]
