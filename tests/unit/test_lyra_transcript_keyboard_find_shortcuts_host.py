from __future__ import annotations

import pytest
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
        ActionRegistry(),
        memory_marker,  # type: ignore[arg-type] -- no memory path
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m129_shortcut_bindings_and_default_search(host) -> None:
    window, provider, _ = host
    assert window.transcript_find_focus_shortcut.objectName() == (
        "lyra_transcript_find_focus_shortcut"
    )
    assert window.transcript_find_next_shortcut.objectName() == (
        "lyra_transcript_find_next_shortcut"
    )
    assert window.transcript_find_previous_shortcut.objectName() == (
        "lyra_transcript_find_previous_shortcut"
    )
    assert window.transcript_find_focus_shortcut.key() == QKeySequence("Ctrl+F")
    assert window.transcript_find_next_shortcut.key() == QKeySequence("F3")
    assert window.transcript_find_previous_shortcut.key() == QKeySequence(
        "Shift+F3"
    )
    assert window.transcript_find_focus_shortcut.isEnabled()
    assert window.transcript_find_next_shortcut.isEnabled()
    assert window.transcript_find_previous_shortcut.isEnabled()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert not window.transcript_find_whole_word.isChecked()
    assert provider.calls == 0


def test_m129_focus_shortcut_preserves_existing_query(host) -> None:
    window, provider, _ = host
    window.show()
    QApplication.processEvents()
    window.input.setFocus()
    QApplication.processEvents()
    window.transcript_find.setText("alpha")
    window.transcript_find_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    assert window.transcript_find.text() == "alpha"
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert provider.calls == 0


def test_m129_next_shortcut_follows_existing_literal_find(host) -> None:
    window, provider, _ = host
    window._lyra("cat catalog cat")
    window.transcript_find.setText("cat")
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert window.transcript_match_position.text() == "Posição: 1 de 3"
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"
    assert provider.calls == 0


def test_m129_previous_shortcut_wraps_in_both_directions(host) -> None:
    window, _, _ = host
    window._lyra("elm elmtree elm")
    window.transcript_find.setText("elm")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_previous_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 2 de 2"
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"


def test_m129_keyboard_search_keeps_whole_word_case_flags(host) -> None:
    window, _, _ = host
    window._lyra("Cat cat catalog Cat CAT")
    window.transcript_find.setText("Cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    assert window.chat.textCursor().selectedText() == "Cat"
    window.transcript_find_previous_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m129_shortcuts_do_not_interpret_regex(host) -> None:
    window, _, _ = host
    window._lyra("AB.C abxc")
    window.transcript_find.setText("AB.C")
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.chat.textCursor().selectedText() == "AB.C"


def test_m129_empty_query_shortcut_remains_no_op(host) -> None:
    window, provider, _ = host
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_find_status.text() == "Busca: informe termo"
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m129_keyboard_search_respects_bounded_count(host) -> None:
    window, _, _ = host
    window._lyra(" ".join(["M129CAP"] * 260))
    window.transcript_find.setText("M129CAP")
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: 1 de 256+"


def test_m129_busy_shortcuts_disabled_and_direct_guards(host) -> None:
    window, provider, _ = host
    window._lyra("Busy target")
    window.transcript_find.setText("Busy")
    window._set_busy(True)
    try:
        assert not window.transcript_find_focus_shortcut.isEnabled()
        assert not window.transcript_find_next_shortcut.isEnabled()
        assert not window.transcript_find_previous_shortcut.isEnabled()
        assert not window.transcript_find.isEnabled()
        old = window.chat.textCursor().selectedText()
        window._find_next_in_transcript()
        window._focus_transcript_find()
        assert window.chat.textCursor().selectedText() == old
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_focus_shortcut.isEnabled()
    assert window.transcript_find_next_shortcut.isEnabled()


def test_m129_manual_buttons_still_operate_after_shortcuts(host) -> None:
    window, _, _ = host
    window._lyra("pin pin")
    window.transcript_find.setText("pin")
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"
    window.transcript_find_previous_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"


def test_m129_cancelled_reset_preserves_shortcuts_and_query(
    host, monkeypatch
) -> None:
    window, _, _ = host
    window._lyra("token token")
    window.transcript_find.setText("token")
    window.transcript_find_next_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "token"
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_find_next_shortcut.isEnabled()


def test_m129_confirmed_reset_clears_find_but_keeps_shortcuts(
    host, monkeypatch
) -> None:
    window, provider, _ = host
    window.transcript_find.setText("token")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_case_sensitive.setChecked(True)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert not window.transcript_find_whole_word.isChecked()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_next_shortcut.isEnabled()
    assert window.transcript_find_focus_shortcut.isEnabled()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert provider.calls == 0


def test_m129_shortcuts_are_independent_between_windows(host) -> None:
    window, provider, _ = host
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        CaptureProvider(), build_default_tool_catalog(),
    )
    try:
        window._lyra("left left")
        other._lyra("right right right")
        window.transcript_find.setText("left")
        other.transcript_find.setText("right")
        window.transcript_find_next_shortcut.activated.emit()
        assert window.transcript_match_count.text() == "Ocorrências: 2"
        assert other.transcript_match_count.text() == "Ocorrências: —"
        other.transcript_find_previous_shortcut.activated.emit()
        assert other.transcript_match_count.text() == "Ocorrências: 3"
        assert window.transcript_match_position.text() == "Posição: 1 de 2"
        assert provider.calls == 0
    finally:
        other.close()


def test_m129_keyboard_shortcuts_do_not_mutate_context_or_draft(host) -> None:
    window, provider, memory = host
    window._lyra("M129CASE")
    window.input.setText("rascunho privado")
    window.transcript_find.setText("M129CASE")
    ctx = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    text = window.chat.toPlainText()
    window.transcript_find_next_shortcut.activated.emit()
    window.transcript_find_previous_shortcut.activated.emit()
    assert window.input.text() == "rascunho privado"
    assert window.chat.toPlainText() == text
    assert window._context.snapshot() == ctx
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert provider.calls == 0
