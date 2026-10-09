from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
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
        raise AssertionError("no continuation expected")

    def reply(self, text, *, history=()):
        raise AssertionError("no direct reply expected")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory_marker = object()
    window = MainWindow(
        ActionRegistry(), memory_marker,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def focus_search(window) -> None:
    window.show()
    window.transcript_find.setFocus()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()


def test_m131_escape_shortcut_identity_and_widget_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.transcript_find_escape_shortcut
    assert shortcut.objectName() == "lyra_transcript_find_escape_shortcut"
    assert shortcut.parent() is window.transcript_find
    assert shortcut.key() == QKeySequence(Qt.Key.Key_Escape)
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    assert shortcut.isEnabled()
    assert provider.calls == 0


def test_m131_direct_escape_returns_focus_only_from_search(host) -> None:
    window, provider, _ = host
    focus_search(window)
    window._leave_transcript_find()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m131_escape_activated_signal_returns_focus(host) -> None:
    window, provider, _ = host
    focus_search(window)
    window.transcript_find_escape_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m131_escape_preserves_query_count_rank_and_status(host) -> None:
    window, provider, _ = host
    window._lyra("violet violet")
    window.transcript_find.setText("violet")
    window.transcript_find_next.click()
    original = (
        window.transcript_find.text(),
        window.transcript_match_count.text(),
        window.transcript_match_position.text(),
        window.transcript_find_status.text(),
        window._last_find_query,
    )
    focus_search(window)
    window._leave_transcript_find()
    assert original == (
        window.transcript_find.text(),
        window.transcript_match_count.text(),
        window.transcript_match_position.text(),
        window.transcript_find_status.text(),
        window._last_find_query,
    )
    assert provider.calls == 0


def test_m131_escape_preserves_modes_and_draft(host) -> None:
    window, provider, _ = host
    window.input.setText("pedido não enviado")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find.setText("word")
    focus_search(window)
    window._leave_transcript_find()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert window.transcript_find.text() == "word"
    assert window.input.text() == "pedido não enviado"
    assert provider.calls == 0


def test_m131_escape_preserves_chat_selection_and_follow(host) -> None:
    window, provider, _ = host
    window._lyra("otter otter")
    window.chat_follow.setChecked(False)
    window.transcript_find.setText("otter")
    window.transcript_find_next.click()
    selection = window.chat.textCursor().selectedText()
    position = window.chat.textCursor().selectionStart()
    follow = window.chat_follow.isChecked()
    focus_search(window)
    window._leave_transcript_find()
    assert window.chat.textCursor().selectedText() == selection
    assert window.chat.textCursor().selectionStart() == position
    assert window.chat_follow.isChecked() == follow
    assert provider.calls == 0


def test_m131_escape_from_composer_does_nothing(host) -> None:
    window, provider, _ = host
    window.show()
    window.input.setFocus()
    QApplication.processEvents()
    assert window.input.hasFocus()
    window.transcript_find.setText("keep")
    window._leave_transcript_find()
    assert window.input.hasFocus()
    assert window.transcript_find.text() == "keep"
    assert provider.calls == 0


def test_m131_busy_direct_handler_and_shortcut_guard(host) -> None:
    window, provider, _ = host
    focus_search(window)
    window._set_busy(True)
    try:
        assert not window.transcript_find_escape_shortcut.isEnabled()
        assert not window.transcript_find.isEnabled()
        assert not window.input.isEnabled()
        window._leave_transcript_find()
        assert not window.input.hasFocus()
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_escape_shortcut.isEnabled()


def test_m131_ctrl_f_then_escape_preserves_query(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("keep")
    window.show()
    window.input.setFocus()
    QApplication.processEvents()
    window.transcript_find_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    window.transcript_find_escape_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.transcript_find.text() == "keep"
    assert provider.calls == 0


def test_m131_escape_then_clear_button_still_works(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("clear")
    focus_search(window)
    window._leave_transcript_find()
    assert window.transcript_find.text() == "clear"
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert provider.calls == 0


def test_m131_empty_query_escape_keeps_neutral_status(host) -> None:
    window, provider, _ = host
    focus_search(window)
    window._leave_transcript_find()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert provider.calls == 0


def test_m131_escape_host_instance_isolation(host) -> None:
    window, provider, _ = host
    second_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        second_provider, build_default_tool_catalog(),
    )
    try:
        window.transcript_find.setText("alpha")
        other.transcript_find.setText("beta")
        focus_search(window)
        window._leave_transcript_find()
        assert window.transcript_find.text() == "alpha"
        assert other.transcript_find.text() == "beta"
        assert other.transcript_find_escape_shortcut.isEnabled()
        assert provider.calls == 0 and second_provider.calls == 0
    finally:
        other.close()


def test_m131_reset_denied_preserves_escape_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.transcript_find.setText("hold")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "hold"
    assert window.transcript_find_escape_shortcut.isEnabled()
    assert provider.calls == 0


def test_m131_reset_accepted_preserves_escape_shortcut(host, monkeypatch) -> None:
    window, provider, memory = host
    window.transcript_find.setText("clear")
    ctx = window._context.snapshot()
    personality = window._personality.snapshot()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_escape_shortcut.isEnabled()
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert window._context.snapshot() == ctx
    assert provider.calls == 0
