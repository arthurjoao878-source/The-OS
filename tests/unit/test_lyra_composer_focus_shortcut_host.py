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
        raise AssertionError("no continuation expected")

    def reply(self, text, *, history=()):
        raise AssertionError("no direct reply expected")


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


def focus_host(window, widget) -> None:
    window.show()
    widget.setFocus()
    QApplication.processEvents()
    assert widget.hasFocus()


def test_m133_identity_parent_and_window_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.composer_focus_shortcut
    assert shortcut.objectName() == "lyra_composer_focus_shortcut"
    assert shortcut.parent() is window
    assert shortcut.key() == QKeySequence("Ctrl+M")
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.isEnabled()
    assert provider.calls == 0


def test_m133_direct_focus_from_chat_preserves_unsent_draft(host) -> None:
    window, provider, _ = host
    window.input.setText("rascunho não enviado")
    focus_host(window, window.chat)
    window._focus_composer()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.input.text() == "rascunho não enviado"
    assert provider.calls == 0


def test_m133_real_ctrl_m_from_chat_uses_window_shortcut(host) -> None:
    window, provider, _ = host
    window.input.setText("texto privado")
    focus_host(window, window.chat)
    QTest.keyClick(window.chat, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.input.text() == "texto privado"
    assert provider.calls == 0


def test_m133_real_ctrl_m_from_find_preserves_search_and_rank(host) -> None:
    window, provider, _ = host
    window._lyra("sol sol")
    window.transcript_find.setText("sol")
    window._find_next_in_transcript()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.input.setText("não enviar")
    focus_host(window, window.transcript_find)
    count = window.transcript_match_count.text()
    rank = window.transcript_match_position.text()
    status = window.transcript_find_status.text()
    selected = window.chat.textCursor().selectedText()
    QTest.keyClick(window.transcript_find, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.transcript_find.text() == "sol"
    assert (window.transcript_match_count.text(), window.transcript_match_position.text(),
            window.transcript_find_status.text()) == (count, rank, status)
    assert window.chat.textCursor().selectedText() == selected
    assert window.input.text() == "não enviar"
    assert provider.calls == 0


def test_m133_signal_activation_moves_only_focus(host) -> None:
    window, provider, _ = host
    focus_host(window, window.chat)
    window.composer_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m133_composer_already_focused_is_idempotent(host) -> None:
    window, provider, _ = host
    window.input.setText("meu texto")
    focus_host(window, window.input)
    window._focus_composer()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.input.text() == "meu texto"
    assert provider.calls == 0


def test_m133_busy_guard_disables_shortcut_and_direct_handler(host) -> None:
    window, provider, _ = host
    focus_host(window, window.chat)
    window.input.setText("não enviar")
    window._set_busy(True)
    try:
        assert not window.input.isEnabled()
        assert not window.composer_focus_shortcut.isEnabled()
        window.chat.setFocus()
        QApplication.processEvents()
        window._focus_composer()
        assert not window.input.hasFocus()
        assert window.input.text() == "não enviar"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.composer_focus_shortcut.isEnabled()


def test_m133_restored_after_busy_and_real_shortcut(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    window._set_busy(False)
    focus_host(window, window.chat)
    QTest.keyClick(window.chat, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m133_preserves_find_modes_and_draft_recall(host) -> None:
    window, provider, _ = host
    window._lyra("Oak oak")
    window.transcript_find.setText("Oak")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window._find_next_in_transcript()
    window.input.setText("não enviar")
    rank = window.transcript_match_position.text()
    window.composer_focus_shortcut.activated.emit()
    assert window.input.text() == "não enviar"
    assert window.transcript_match_position.text() == rank
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert provider.calls == 0


def test_m133_ctrl_f_and_escape_still_retain_expected_scopes(host) -> None:
    window, provider, _ = host
    focus_host(window, window.input)
    window.input.setText("draft")
    QTest.keyClick(window.input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    QTest.keyClick(window.transcript_find, Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.input.text() == "draft"
    assert provider.calls == 0


def test_m133_separate_window_shortcuts_have_distinct_owners(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.show()
        other.show()
        window.input.setText("first")
        other.input.setText("second")
        window.composer_focus_shortcut.activated.emit()
        assert window.input.text() == "first"
        assert other.input.text() == "second"
        assert other.composer_focus_shortcut is not window.composer_focus_shortcut
        assert other.composer_focus_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m133_reset_denied_keeps_query_draft_and_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.transcript_find.setText("keep")
    window.input.setText("keep draft")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.input.text() == "keep draft"
    assert window.transcript_find.text() == "keep"
    assert window.composer_focus_shortcut.isEnabled()
    assert provider.calls == 0


def test_m133_reset_accepted_preserves_shortcut_and_personality(host, monkeypatch) -> None:
    window, provider, memory = host
    snapshot = window._personality.snapshot()
    window.input.setText("draft")
    window.transcript_find.setText("search")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.input.text() == ""
    assert window.transcript_find.text() == ""
    assert window.composer_focus_shortcut.isEnabled()
    assert window._personality.snapshot() == snapshot
    assert window._memory is memory
    assert provider.calls == 0


def test_m133_preserves_provider_history_and_perception(host) -> None:
    window, provider, memory = host
    before_context = window._context.provider_snapshot()
    before_personality = window._personality.snapshot()
    perception = window._perception
    window.composer_focus_shortcut.activated.emit()
    assert window._context.provider_snapshot() == before_context
    assert window._personality.snapshot() == before_personality
    assert window._perception is perception
    assert window._memory is memory
    assert provider.calls == 0


def test_m133_does_not_bypass_input_length_limit(host) -> None:
    window, provider, _ = host
    window.input.setText("a" * 5000)
    assert len(window.input.text()) == 4096
    window.composer_focus_shortcut.activated.emit()
    assert len(window.input.text()) == 4096
    assert provider.calls == 0
