from __future__ import annotations

import pytest
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


def test_m130_clear_button_identity_and_default_state(host) -> None:
    window, provider, _ = host
    button = window.transcript_find_clear
    assert button.objectName() == "lyra_transcript_find_clear"
    assert button.text() == "Limpar busca"
    assert button.isEnabled()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m130_click_clears_query_and_count_after_explicit_find(host) -> None:
    window, provider, _ = host
    window._lyra("violet violet")
    window.transcript_find.setText("violet")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window._last_find_query is None
    assert provider.calls == 0


def test_m130_clear_without_search_does_not_scan(host) -> None:
    window, provider, _ = host
    window._lyra("pine pine")
    window.transcript_find.setText("pine")
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert provider.calls == 0


def test_m130_clear_empty_query_restores_neutral_labels(host) -> None:
    window, provider, _ = host
    window.transcript_find_next.click()
    assert window.transcript_find_status.text() == "Busca: informe termo"
    window.transcript_find_clear.click()
    window.transcript_find_clear.click()
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m130_clear_preserves_case_and_whole_word_settings(host) -> None:
    window, provider, _ = host
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find.setText("Word")
    window.transcript_find_clear.click()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert window.transcript_find.text() == ""
    assert provider.calls == 0


def test_m130_clear_preserves_transcript_selection(host) -> None:
    window, _, _ = host
    window._lyra("otter otter")
    window.transcript_find.setText("otter")
    window.transcript_find_next.click()
    selection = window.chat.textCursor().selectedText()
    position = window.chat.textCursor().selectionStart()
    assert selection == "otter"
    window.transcript_find_clear.click()
    assert window.chat.textCursor().selectedText() == selection
    assert window.chat.textCursor().selectionStart() == position


def test_m130_clear_preserves_scroll_follow_and_draft(host) -> None:
    window, provider, _ = host
    window._lyra("many words in the visible transcript")
    window.input.setText("pedido ainda não enviado")
    window.chat_follow.setChecked(False)
    window.transcript_find.setText("words")
    scrollbar = window.chat.verticalScrollBar()
    before_scroll = scrollbar.value()
    before_follow = window.chat_follow.isChecked()
    window.transcript_find_clear.click()
    assert window.input.text() == "pedido ainda não enviado"
    assert window.chat_follow.isChecked() == before_follow
    assert scrollbar.value() == before_scroll
    assert provider.calls == 0


def test_m130_clear_preserves_context_personality_and_memory(host) -> None:
    window, provider, memory = host
    window._lyra("M130TOKEN")
    window.transcript_find.setText("M130TOKEN")
    ctx = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    transcript = window.chat.toPlainText()
    window.transcript_find_clear.click()
    assert window._context.snapshot() == ctx
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window.chat.toPlainText() == transcript
    assert window._memory is memory
    assert provider.calls == 0


def test_m130_clear_then_next_query_resets_search_origin(host) -> None:
    window, _, _ = host
    window._lyra("lily lily lily")
    window.transcript_find.setText("lily")
    window.transcript_find_next.click()
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"
    window.transcript_find_clear.click()
    window.transcript_find.setText("lily")
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 3"


def test_m130_busy_button_and_direct_handler_are_guarded(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("guard")
    window._set_busy(True)
    try:
        assert not window.transcript_find_clear.isEnabled()
        assert not window.transcript_find.isEnabled()
        window._clear_transcript_find()
        window.transcript_find_clear.click()
        assert window.transcript_find.text() == "guard"
        assert window.transcript_find_status.text() == "Busca: pronta"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_clear.isEnabled()
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""


def test_m130_clear_does_not_reset_keyboard_shortcuts(host) -> None:
    window, _, _ = host
    window.transcript_find.setText("abc")
    window.transcript_find_clear.click()
    assert window.transcript_find_focus_shortcut.isEnabled()
    assert window.transcript_find_next_shortcut.isEnabled()
    assert window.transcript_find_previous_shortcut.isEnabled()
    window.transcript_find_focus_shortcut.activated.emit()
    assert window.transcript_find.text() == ""


def test_m130_cancelled_session_reset_preserves_query_until_clear(
    host, monkeypatch
) -> None:
    window, provider, _ = host
    window.transcript_find.setText("hold")
    window.transcript_find_whole_word.setChecked(True)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "hold"
    assert window.transcript_find_whole_word.isChecked()
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_whole_word.isChecked()
    assert provider.calls == 0


def test_m130_confirmed_session_reset_preserves_button(host, monkeypatch) -> None:
    window, provider, _ = host
    window.transcript_find.setText("clear")
    window.transcript_find_case_sensitive.setChecked(True)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert not window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_clear.isEnabled()
    window.transcript_find_clear.click()
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert provider.calls == 0


def test_m130_clear_isolated_between_two_windows(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window._lyra("alpha alpha")
        other._lyra("beta beta")
        window.transcript_find.setText("alpha")
        other.transcript_find.setText("beta")
        other.transcript_find_next.click()
        assert other.transcript_match_count.text() == "Ocorrências: 2"
        window.transcript_find_clear.click()
        assert window.transcript_find.text() == ""
        assert other.transcript_find.text() == "beta"
        assert other.transcript_match_count.text() == "Ocorrências: 2"
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert provider.calls == 0
        assert other_provider.calls == 0
    finally:
        other.close()
