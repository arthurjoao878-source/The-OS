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
        memory_marker,  # type: ignore[arg-type] -- no memory route
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m128_default_off_preserves_legacy_labels(host) -> None:
    window, provider, _ = host
    assert window.transcript_find_whole_word.objectName() == (
        "lyra_transcript_find_whole_word"
    )
    assert not window.transcript_find_whole_word.isChecked()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m128_default_substring_find_still_works(host) -> None:
    window, _, _ = host
    window._lyra("cat catalog cat")
    window.transcript_find.setText("cat")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert window.transcript_match_position.text() == "Posição: 1 de 3"


def test_m128_whole_word_excludes_substrings(host) -> None:
    window, _, _ = host
    window._lyra("cat catalog cat")
    window.transcript_find.setText("cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m128_case_sensitive_and_whole_word_compose(host) -> None:
    window, _, _ = host
    window._lyra("Cat cat catalog Cat CAT")
    window.transcript_find.setText("Cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 4"
    window.transcript_find_case_sensitive.setChecked(True)
    assert window.transcript_match_count.text() == "Ocorrências: —"
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    assert window.chat.textCursor().selectedText() == "Cat"


def test_m128_toggle_invalidates_without_scanning(host, monkeypatch) -> None:
    window, provider, _ = host
    window._lyra("token tokenish token")
    window.transcript_find.setText("token")
    window.transcript_find_next.click()
    selected = window.chat.textCursor().selectedText()
    query = window.transcript_find.text()
    monkeypatch.setattr(
        window,
        "_update_transcript_match_count",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scan")),
    )
    window.transcript_find_whole_word.setChecked(True)
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window.chat.textCursor().selectedText() == selected
    assert window.transcript_find.text() == query
    assert provider.calls == 0


def test_m128_whole_word_next_previous_wrap(host) -> None:
    window, _, _ = host
    window._lyra("elm elmtree elm")
    window.transcript_find.setText("elm")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"


def test_m128_whole_word_punctuation_delimits_tokens(host) -> None:
    window, _, _ = host
    window._lyra("cat, cat! (cat) catalog")
    window.transcript_find.setText("cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert window.chat.textCursor().selectedText() == "cat"


def test_m128_find_remains_literal_not_regex(host) -> None:
    window, _, _ = host
    window._lyra("AB.C abxc")
    window.transcript_find.setText("AB.C")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.chat.textCursor().selectedText() == "AB.C"


def test_m128_whole_word_zero_and_query_clear(host) -> None:
    window, _, _ = host
    window._lyra("catalog")
    window.transcript_find.setText("cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 0"
    assert window.transcript_match_position.text() == "Posição: —"
    window.transcript_find.clear()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"


def test_m128_whole_word_bounded_256plus_and_rank(host) -> None:
    window, _, _ = host
    window._lyra(" ".join(["M128CAP"] * 260) + " M128CAPsuffix")
    window.transcript_find.setText("M128CAP")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: 1 de 256+"
    window._last_find_query = "M128CAP"
    cursor = window.chat.textCursor()
    cursor.setPosition(window.chat.toPlainText().rfind("M128CAP ") - 1)
    window.chat.setTextCursor(cursor)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: >256 de 256+"


def test_m128_query_and_transcript_limits_fail_closed(host) -> None:
    window, _, _ = host
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find.setMaxLength(200)
    window.transcript_find.setText("X" * 121)
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"
    window.transcript_find.setText("X")
    window.chat.setPlainText("X" * 65537)
    window._find_previous_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"


def test_m128_busy_whole_word_control_and_direct_find_guard(host) -> None:
    window, provider, _ = host
    window._lyra("Busy")
    window.transcript_find.setText("Busy")
    window._set_busy(True)
    try:
        assert not window.transcript_find_whole_word.isEnabled()
        assert not window.transcript_find_case_sensitive.isEnabled()
        window._find_next_in_transcript()
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert window.transcript_match_position.text() == "Posição: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_whole_word.isEnabled()


def test_m128_rejected_reset_preserves_whole_word_mode(host, monkeypatch) -> None:
    window, _, _ = host
    window._lyra("Cat catting")
    window.transcript_find.setText("Cat")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_next.click()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find_whole_word.isChecked()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.transcript_match_position.text() == "Posição: 1 de 1"


def test_m128_confirmed_reset_restores_default_isolated(host, monkeypatch) -> None:
    window, provider, _ = host
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        CaptureProvider(), build_default_tool_catalog(),
    )
    try:
        window.transcript_find_whole_word.setChecked(True)
        other.transcript_find_whole_word.setChecked(True)
        window.transcript_find_case_sensitive.setChecked(True)
        window.transcript_find.setText("Cat")
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )
        window.session_reset.click()
        assert not window.transcript_find_whole_word.isChecked()
        assert not window.transcript_find_case_sensitive.isChecked()
        assert window.transcript_find.text() == ""
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert window.transcript_match_position.text() == "Posição: —"
        assert other.transcript_find_whole_word.isChecked()
        assert provider.calls == 0
    finally:
        other.close()


def test_m128_passive_mode_no_context_memory_draft_changes(host) -> None:
    window, provider, memory_marker = host
    window._lyra("Token token tokenized")
    window.input.setText("rascunho privado")
    context = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    visible = window.chat.toPlainText()
    window.transcript_find.setText("Token")
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window._context.snapshot() == context
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory_marker
    assert window.input.text() == "rascunho privado"
    assert window.chat.toPlainText() == visible
    assert provider.calls == 0
