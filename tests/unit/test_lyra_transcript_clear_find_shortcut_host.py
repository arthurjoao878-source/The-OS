from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="ok", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("unexpected continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected direct provider reply")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory
    finally:
        window.close()


def focus(window, widget) -> None:
    window.show()
    widget.setFocus()
    QApplication.processEvents()
    assert widget.hasFocus()


def press_clear(widget) -> None:
    QTest.keyClick(
        widget, Qt.Key.Key_L,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m139_identity_and_window_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.transcript_find_clear_shortcut
    assert shortcut.objectName() == "lyra_transcript_find_clear_shortcut"
    assert shortcut.parent() is window
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.key() == QKeySequence("Ctrl+Shift+L")
    assert shortcut.isEnabled()
    assert provider.calls == 0


def test_m139_handler_clears_only_query(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    window._clear_transcript_find_shortcut()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert provider.calls == 0


def test_m139_signal_clears_query_and_labels(host) -> None:
    window, provider, _ = host
    window._lyra("cat cat")
    window.transcript_find.setText("cat")
    window._find_next_in_transcript()
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window._last_find_query is None
    assert provider.calls == 0


def test_m139_real_qt_composer_preserves_draft_and_focus(host) -> None:
    window, provider, _ = host
    window.input.setText("rascunho importante")
    window.transcript_find.setText("casa")
    focus(window, window.input)
    press_clear(window.input)
    assert window.transcript_find.text() == ""
    assert window.input.text() == "rascunho importante"
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m139_real_qt_search_keeps_focus(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    focus(window, window.transcript_find)
    press_clear(window.transcript_find)
    assert window.transcript_find.text() == ""
    assert window.transcript_find.hasFocus()
    assert provider.calls == 0


def test_m139_preserves_transcript_selection(host) -> None:
    window, provider, _ = host
    window._lyra("alpha alpha")
    window.transcript_find.setText("alpha")
    window._find_next_in_transcript()
    selected = window.chat.textCursor().selectedText()
    assert selected == "alpha"
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.chat.textCursor().selectedText() == selected
    assert window.transcript_find.text() == ""
    assert provider.calls == 0


def test_m139_empty_search_is_idempotent(host) -> None:
    window, provider, _ = host
    window.transcript_find_clear_shortcut.activated.emit()
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m139_preserves_search_modes(host) -> None:
    window, provider, _ = host
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find.setText("Cat")
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert window.transcript_find.text() == ""
    assert provider.calls == 0


def test_m139_real_qt_transcript_read_only(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("cat")
    focus(window, window.chat)
    press_clear(window.chat)
    assert window.transcript_find.text() == ""
    assert window.chat.isReadOnly()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m139_existing_find_works_after_clear(host) -> None:
    window, provider, _ = host
    window._lyra("alpha alpha")
    window.transcript_find.setText("alpha")
    window.transcript_find_clear_shortcut.activated.emit()
    window.transcript_find.setText("alpha")
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.chat.textCursor().selectedText() == "alpha"
    assert provider.calls == 0


def test_m139_busy_handler_signal_and_qt_fail_closed(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    focus(window, window.chat)
    window._set_busy(True)
    try:
        assert not window.transcript_find_clear_shortcut.isEnabled()
        window._clear_transcript_find_shortcut()
        window.transcript_find_clear_shortcut.activated.emit()
        press_clear(window.chat)
        assert window.transcript_find.text() == "casa"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_clear_shortcut.isEnabled()


def test_m139_real_key_reenabled_after_busy(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    window._set_busy(True)
    window._set_busy(False)
    focus(window, window.input)
    press_clear(window.input)
    assert window.transcript_find.text() == ""
    assert provider.calls == 0


def test_m139_two_window_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.transcript_find.setText("primary")
        other.transcript_find.setText("secondary")
        window.transcript_find_clear_shortcut.activated.emit()
        assert window.transcript_find.text() == ""
        assert other.transcript_find.text() == "secondary"
        assert other.transcript_find_clear_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m139_denied_reset_preserves_query_and_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "casa"
    assert window.transcript_find_clear_shortcut.isEnabled()
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.transcript_find.text() == ""
    assert provider.calls == 0


def test_m139_accepted_reset_keeps_shortcut(host, monkeypatch) -> None:
    window, provider, memory = host
    personality = window._personality.snapshot()
    window.transcript_find.setText("casa")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_clear_shortcut.isEnabled()
    window.transcript_find.setText("nova")
    window.transcript_find_clear_shortcut.activated.emit()
    assert window.transcript_find.text() == ""
    assert window._memory is memory
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m139_no_provider_memory_context_or_task_side_effect(host) -> None:
    window, provider, memory = host
    before = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    transcript = window.chat.toPlainText()
    window.transcript_find.setText("casa")
    window.transcript_find_clear_shortcut.activated.emit()
    assert window._context.provider_snapshot() == before
    assert window._personality.snapshot() == personality
    assert window._perception is perception
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
