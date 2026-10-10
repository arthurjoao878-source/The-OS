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
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView


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


def _key(window, target) -> None:
    window.show()
    target.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        target,
        Qt.Key.Key_I,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m148_identity_scope_and_key(host) -> None:
    window, provider, _, _ = host
    shortcut = window.task_timeline_interruptions_shortcut
    assert shortcut.objectName() == "lyra_task_timeline_interruptions_shortcut"
    assert shortcut.key().toString() == "Ctrl+Shift+I"
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.parent() is window
    assert provider.calls == 0


def test_m148_unchecked_default_and_enabled(host) -> None:
    window, _, _, _ = host
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruptions_shortcut.isEnabled()
    assert window.task_timeline_view.isHidden()


def test_m148_signal_checks_filter(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()


def test_m148_signal_roundtrip_unchecks_filter(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_real_key_from_composer(host) -> None:
    window, provider, _, dry = host
    _key(window, window.input)
    assert window.task_timeline_interruptions_only.isChecked()
    assert provider.calls == 0 and not dry.workers


def test_m148_real_key_composer_roundtrip(host) -> None:
    window, _, _, _ = host
    _key(window, window.input)
    _key(window, window.input)
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_real_key_from_find_preserves_query(host) -> None:
    window, _, _, _ = host
    window.transcript_find.setText("PRIVATE_FIND")
    _key(window, window.transcript_find)
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.transcript_find.text() == "PRIVATE_FIND"


def test_m148_real_key_from_read_only_transcript(host) -> None:
    window, _, _, _ = host
    _key(window, window.chat)
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.chat.isReadOnly()


def test_m148_click_and_shortcut_share_filter_state(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_only.click()
    assert window.task_timeline_interruptions_only.isChecked()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_disabled_checkbox_direct_guard(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_only.setEnabled(False)
    window._toggle_task_timeline_interruptions_shortcut()
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_disabled_shortcut_direct_guard(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.setEnabled(False)
    window._toggle_task_timeline_interruptions_shortcut()
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_reenabled_shortcut_works(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.setEnabled(False)
    window._toggle_task_timeline_interruptions_shortcut()
    window.task_timeline_interruptions_shortcut.setEnabled(True)
    window._toggle_task_timeline_interruptions_shortcut()
    assert window.task_timeline_interruptions_only.isChecked()


def test_m148_filtered_view_does_not_mutate_history_or_summary(host) -> None:
    window, provider, _, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    summary, events = window.task_summary.text(), window._task_timeline.snapshot()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == "Sem interrupções nos eventos recentes."
    assert window.task_summary.text() == summary
    assert window._task_timeline.snapshot() == events
    assert provider.calls == 0 and not dry.workers


def test_m148_filtered_failure_visible_with_original_number(host) -> None:
    window, _, _, _ = host
    window._task_timeline.record(HostWorkflowProgressView("Tarefa: iniciada · 0/4 etapas", terminal=False))
    window._task_timeline.record(HostWorkflowProgressView("Tarefa: falha no processamento · efeito não comprovado", terminal=True))
    window._refresh_task_timeline()
    window.task_timeline_interruptions_shortcut.activated.emit()
    display = window.task_timeline_view.toPlainText()
    assert display.startswith("2. Tarefa: falha no processamento")
    assert "1. Tarefa: iniciada" not in display
    assert len(window._task_timeline.snapshot()) == 2


def test_m148_filter_hidden_panel_unchanged(host) -> None:
    window, _, _, _ = host
    assert window.task_timeline_view.isHidden()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_interruptions_only.isChecked()


def test_m148_panel_toggle_shortcut_compatible(host) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_interruptions_only.isChecked()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_interruptions_only.isChecked()


def test_m148_preserves_draft_find_follow_personality(host) -> None:
    window, _, _, _ = host
    window.input.setText("PRIVATE_DRAFT")
    window.transcript_find.setText("PRIVATE_FIND")
    window.chat_follow.setChecked(False)
    window.personality_tone.setCurrentIndex(1)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.input.text() == "PRIVATE_DRAFT"
    assert window.transcript_find.text() == "PRIVATE_FIND"
    assert not window.chat_follow.isChecked()
    assert window.personality_tone.currentIndex() == 1


def test_m148_busy_worker_shortcut_does_not_dispatch(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE_TASK", ())
    assert len(dry.workers) == 1
    control = window._active_control
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window._active_control is control
    assert len(dry.workers) == 1 and provider.calls == 0


def test_m148_window_isolation(host) -> None:
    window, _, _, _ = host
    other = MainWindow(
        ActionRegistry(), object(),  # type: ignore[arg-type]
        ControlledProvider(), build_default_tool_catalog(),
    )
    try:
        window.task_timeline_interruptions_shortcut.activated.emit()
        assert window.task_timeline_interruptions_only.isChecked()
        assert not other.task_timeline_interruptions_only.isChecked()
        other.task_timeline_interruptions_shortcut.activated.emit()
        assert other.task_timeline_interruptions_only.isChecked()
        assert window.task_timeline_interruptions_only.isChecked()
    finally:
        other.close()


def test_m148_denied_reset_preserves_filter(host, monkeypatch) -> None:
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.task_timeline_interruptions_only.isChecked()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m148_accepted_reset_preserves_shortcut_and_memory(host, monkeypatch) -> None:
    window, provider, memory, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    window.task_timeline_interruptions_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers


def test_m148_no_provider_memory_real_action_or_new_authority(host) -> None:
    window, provider, memory, dry = host
    for _ in range(8):
        window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert provider.calls == 0 and not dry.workers
    assert window._memory is memory
    assert window._active_control is None
    assert window._active_direct_action is None
