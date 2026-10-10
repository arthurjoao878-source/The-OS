from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.main_window import MainWindow


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("provider continuation not authorized")

    def reply(self, text, *, history=()):
        raise AssertionError("provider reply not authorized")


class DryPool:
    def __init__(self) -> None:
        self.workers: list[object] = []

    def start(self, worker) -> None:
        self.workers.append(worker)


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = ControlledProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def test_m147_shortcut_identity_and_window_scope(host) -> None:
    window, provider, _, _ = host
    shortcut = window.task_timeline_toggle_shortcut
    assert shortcut.objectName() == "lyra_task_timeline_toggle_shortcut"
    assert shortcut.key().toString() == "Ctrl+Shift+E"
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.parent() is window
    assert provider.calls == 0


def test_m147_hidden_by_default(host) -> None:
    window, _, _, _ = host
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_toggle_shortcut.isEnabled()


def test_m147_shortcut_signal_opens_panel(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()


def test_m147_shortcut_signal_closes_panel(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle_shortcut.activated.emit()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()


def test_m147_real_qt_keyboard_opens_from_composer(host) -> None:
    window, provider, _, dry = host
    window.show()
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        window.input,
        Qt.Key.Key_E,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    assert provider.calls == 0 and not dry.workers


def test_m147_real_qt_keyboard_roundtrip_from_composer(host) -> None:
    window, _, _, _ = host
    window.show()
    window.input.setFocus()
    QApplication.processEvents()
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    QTest.keyClick(window.input, Qt.Key.Key_E, modifiers)
    QTest.keyClick(window.input, Qt.Key.Key_E, modifiers)
    QApplication.processEvents()
    assert window.task_timeline_view.isHidden()


def test_m147_button_and_shortcut_share_visibility(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle.click()
    assert not window.task_timeline_view.isHidden()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()


def test_m147_disabled_button_blocks_direct_handler(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle.setEnabled(False)
    window._toggle_task_timeline_shortcut()
    assert window.task_timeline_view.isHidden()


def test_m147_disabled_shortcut_blocks_direct_handler(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle_shortcut.setEnabled(False)
    window._toggle_task_timeline_shortcut()
    assert window.task_timeline_view.isHidden()


def test_m147_reenabled_shortcut_restores_toggle(host) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle_shortcut.setEnabled(False)
    window._toggle_task_timeline_shortcut()
    window.task_timeline_toggle_shortcut.setEnabled(True)
    window._toggle_task_timeline_shortcut()
    assert not window.task_timeline_view.isHidden()


def test_m147_keyboard_keeps_summary_and_history(host) -> None:
    window, provider, _, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    summary = window.task_summary.text()
    events = window._task_timeline.snapshot()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_summary.text() == summary
    assert window._task_timeline.snapshot() == events
    assert "PRIVATE" not in window.task_timeline_view.toPlainText()
    assert provider.calls == 0 and not dry.workers


def test_m147_shortcut_preserves_interruption_filter(host) -> None:
    window, _, _, _ = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    window.task_timeline_interruptions_only.setChecked(True)
    filtered = window.task_timeline_view.toPlainText()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == filtered


def test_m147_shortcut_preserves_draft_and_search(host) -> None:
    window, _, _, _ = host
    window.input.setText("rascunho importante")
    window.transcript_find.setText("termo de busca")
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.input.text() == "rascunho importante"
    assert window.transcript_find.text() == "termo de busca"


def test_m147_shortcut_preserves_follow_and_personality(host) -> None:
    window, _, _, _ = host
    window.chat_follow.setChecked(False)
    window.personality_tone.setCurrentIndex(1)
    tone = window.personality_tone.currentIndex()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.chat_follow.isChecked()
    assert window.personality_tone.currentIndex() == tone


def test_m147_shortcut_available_during_busy_dry_task(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE_TASK", ())
    assert len(dry.workers) == 1
    window._toggle_task_timeline_shortcut()
    assert not window.task_timeline_view.isHidden()
    assert provider.calls == 0


def test_m147_shortcut_does_not_change_running_control(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE_TASK", ())
    control = window._active_control
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window._active_control is control
    assert len(dry.workers) == 1 and provider.calls == 0


def test_m147_shortcut_two_window_isolation(host) -> None:
    window, _, _, _ = host
    other = MainWindow(
        ActionRegistry(), object(),  # type: ignore[arg-type]
        ControlledProvider(), build_default_tool_catalog(),
    )
    try:
        window.task_timeline_toggle_shortcut.activated.emit()
        assert not window.task_timeline_view.isHidden()
        assert other.task_timeline_view.isHidden()
        other.task_timeline_toggle_shortcut.activated.emit()
        assert not other.task_timeline_view.isHidden()
        assert not window.task_timeline_view.isHidden()
    finally:
        other.close()


def test_m147_denied_reset_preserves_panel_and_shortcut(host, monkeypatch) -> None:
    window, _, _, _ = host
    window.task_timeline_toggle_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert not window.task_timeline_view.isHidden()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()


def test_m147_accepted_reset_preserves_keyboard_toggle(host, monkeypatch) -> None:
    window, provider, memory, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    window.task_timeline_toggle_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()
    assert window.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers


def test_m147_shortcut_never_requests_provider_or_real_action(host) -> None:
    window, provider, _, dry = host
    for _ in range(6):
        window.task_timeline_toggle_shortcut.activated.emit()
    assert provider.calls == 0
    assert not dry.workers
    assert window._active_control is None
    assert window._active_direct_action is None


def test_m147_window_shortcut_not_application_global(host) -> None:
    window, _, _, _ = host
    assert window.task_timeline_toggle_shortcut.context() is Qt.ShortcutContext.WindowShortcut
    assert window.task_timeline_toggle_shortcut.parent() is window
