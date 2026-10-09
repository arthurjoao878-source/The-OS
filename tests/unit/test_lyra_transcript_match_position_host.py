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


def test_m126_default_position_is_neutral(host) -> None:
    window, provider, _ = host
    assert (
        window.transcript_match_position.objectName()
        == "lyra_transcript_match_position"
    )
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert provider.calls == 0


def test_m126_next_advances_rank_in_three_matches(host) -> None:
    window, _, _ = host
    window._lyra("m126alpha m126alpha m126alpha")
    window.transcript_find.setText("m126alpha")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert window.transcript_match_position.text() == "Posição: 1 de 3"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 3 de 3"


def test_m126_previous_begins_at_last_and_moves_backward(host) -> None:
    window, _, _ = host
    window._lyra("m126beta m126beta m126beta")
    window.transcript_find.setText("m126beta")
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 3 de 3"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"


def test_m126_wrap_navigation_reports_correct_rank(host) -> None:
    window, _, _ = host
    window._lyra("m126gamma m126gamma")
    window.transcript_find.setText("m126gamma")
    window.transcript_find_next.click()
    window.transcript_find_next.click()
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m126_literal_case_insensitive_rank(host) -> None:
    window, _, _ = host
    window._lyra("a.b A.B axb")
    window.transcript_find.setText("a.b")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m126_zero_matches_query_edit_and_empty_are_neutral(host) -> None:
    window, _, _ = host
    window.transcript_find.setText("absent_m126")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 0"
    assert window.transcript_match_position.text() == "Posição: —"
    window._lyra("m126hit")
    window.transcript_find.setText("m126hit")
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 1"
    window.transcript_find.setText("unmatched")
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    window.transcript_find.clear()
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: —"


def test_m126_bounded_rank_when_more_than_256_matches(host) -> None:
    window, _, _ = host
    window._lyra(" ".join(["m126cap"] * 280))
    window.transcript_find.setText("m126cap")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: 1 de 256+"
    window._last_find_query = "m126cap"
    cursor = window.chat.textCursor()
    cursor.setPosition(window.chat.toPlainText().rfind("m126cap") - 1)
    window.chat.setTextCursor(cursor)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: >256 de 256+"


def test_m126_transcript_over_limit_rejected_without_rank(host) -> None:
    window, _, _ = host
    window.chat.setPlainText("X" * 65537)
    window.transcript_find.setText("X")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"
    assert window.transcript_find_status.text() == "Busca: conversa acima do limite"


def test_m126_oversized_query_direct_guard_rejected(host) -> None:
    window, _, _ = host
    window._lyra("X" * 150)
    window.transcript_find.setMaxLength(200)
    window.transcript_find.setText("X" * 121)
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"
    assert window.transcript_find_status.text() == "Busca: termo acima do limite"


def test_m126_busy_find_cannot_change_position(host) -> None:
    window, provider, _ = host
    window._lyra("m126busy")
    window.transcript_find.setText("m126busy")
    window._set_busy(True)
    try:
        window._find_next_in_transcript()
        assert window.transcript_match_position.text() == "Posição: —"
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)


def test_m126_position_is_passive_and_preserves_selection(host) -> None:
    window, provider, memory_marker = host
    window._lyra("m126passive m126passive")
    window.input.setText("Rascunho privado")
    context = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    visible = window.chat.toPlainText()
    window.transcript_find.setText("m126passive")
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    assert window.chat.textCursor().selectedText().lower() == "m126passive"
    assert window._context.snapshot() == context
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory_marker
    assert window.chat.toPlainText() == visible
    assert window.input.text() == "Rascunho privado"
    assert provider.calls == 0


def test_m126_denied_reset_preserves_position(host, monkeypatch) -> None:
    window, _, _ = host
    window._lyra("m126reset")
    window.transcript_find.setText("m126reset")
    window.transcript_find_next.click()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "m126reset"
    assert window.transcript_match_position.text() == "Posição: 1 de 1"


def test_m126_approved_reset_isolates_windows(host, monkeypatch) -> None:
    window, provider, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory route
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window._lyra("m126reset")
        window.transcript_find.setText("m126reset")
        window.transcript_find_next.click()
        other._lyra("m126other m126other")
        other.transcript_find.setText("m126other")
        other.transcript_find_next.click()
        assert other.transcript_match_position.text() == "Posição: 1 de 2"
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        window.session_reset.click()
        assert window.transcript_find.text() == ""
        assert window.transcript_match_position.text() == "Posição: —"
        assert window._context.snapshot() == ()
        assert other.transcript_match_position.text() == "Posição: 1 de 2"
        assert provider.calls == 0
    finally:
        other.close()
