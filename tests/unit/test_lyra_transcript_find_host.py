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
        memory_marker,  # type: ignore[arg-type] -- memory path not used
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m119_find_controls_are_explicit_and_read_only(host) -> None:
    window, _, _ = host
    assert window.transcript_find.objectName() == "lyra_transcript_find"
    assert window.transcript_find_next.objectName() == "lyra_transcript_find_next"
    assert window.transcript_find_previous.objectName() == "lyra_transcript_find_previous"
    assert window.chat.isReadOnly()
    assert window.transcript_find_status.text() == "Busca: pronta"


def test_m119_next_selects_literal_match_and_wraps(host) -> None:
    window, _, _ = host
    window._lyra("Lima e Lima")
    window.transcript_find.setText("Lima")
    window.transcript_find_next.click()
    first = window.chat.textCursor()
    assert first.selectedText() == "Lima"
    window.transcript_find_next.click()
    second = window.chat.textCursor()
    assert second.selectedText() == "Lima"
    assert second.selectionStart() > first.selectionStart()
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectionStart() == first.selectionStart()


def test_m119_previous_starts_at_last_match_and_wraps(host) -> None:
    window, _, _ = host
    window._lyra("Zebra Zebra")
    window.transcript_find.setText("Zebra")
    window.transcript_find_previous.click()
    last = window.chat.textCursor()
    assert last.selectedText() == "Zebra"
    window.transcript_find_previous.click()
    first = window.chat.textCursor()
    assert first.selectedText() == "Zebra"
    assert first.selectionStart() < last.selectionStart()
    window.transcript_find_previous.click()
    assert window.chat.textCursor().selectionStart() == last.selectionStart()


def test_m119_search_is_case_insensitive_and_literal(host) -> None:
    window, _, _ = host
    window._lyra("Fim a.b final")
    window.transcript_find.setText("FIM")
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectedText() == "Fim"
    window.transcript_find.setText("a.b")
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectedText() == "a.b"


def test_m119_no_match_reports_only_neutral_status(host) -> None:
    window, _, _ = host
    window._lyra("PRIVATE_VISIBLE_TRANSCRIPT")
    window.transcript_find.setText("absent-string")
    window.transcript_find_next.click()
    assert window.transcript_find_status.text() == "Busca: nenhum resultado"
    assert "PRIVATE_VISIBLE_TRANSCRIPT" not in window.transcript_find_status.text()
    assert "absent-string" not in window.transcript_find_status.text()


def test_m119_query_limit_is_enforced_and_long_transcripts_fail_closed(host) -> None:
    window, _, _ = host
    window.transcript_find.setText("Q" * 250)
    assert len(window.transcript_find.text()) == 120
    window._lyra("Z" * 65537)
    window.transcript_find_next.click()
    assert window.transcript_find_status.text() == "Busca: conversa acima do limite"
    assert window.chat.isReadOnly()


def test_m119_find_is_passive_and_does_not_modify_context_or_provider(host) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Mensagem anterior")
    before_session = window._context.snapshot()
    before_perception = window._perception.snapshot()
    before_personality = window._personality.snapshot()
    window._lyra("Fragmento para buscar")
    window.transcript_find.setText("Fragmento")
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectedText() == "Fragmento"
    assert window._context.snapshot() == before_session
    assert window._perception.snapshot() == before_perception
    assert window._personality.snapshot() == before_personality
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m119_find_is_disabled_while_host_busy_even_if_slot_invoked(host) -> None:
    window, _, _ = host
    window._lyra("nao buscar enquanto ocupado")
    window.transcript_find.setText("ocupado")
    original = window.chat.textCursor()
    window._set_busy(True)
    try:
        assert not window.transcript_find.isEnabled()
        assert not window.transcript_find_next.isEnabled()
        assert not window.transcript_find_previous.isEnabled()
        window._find_in_transcript(backward=False)
        assert window.chat.textCursor().position() == original.position()
    finally:
        window._set_busy(False)
    assert window.transcript_find.isEnabled()


def test_m119_new_conversation_clears_find_state_without_persisted_changes(
    host, monkeypatch
) -> None:
    window, provider, memory_marker = host
    personality_before = window._personality.snapshot()
    window._lyra("Temporario para busca")
    window.transcript_find.setText("Temporario")
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectedText() == "Temporario"
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window.chat.textCursor().selectedText() == ""
    assert window._memory is memory_marker
    assert window._personality.snapshot() == personality_before
    assert provider.calls == 0


def test_m119_two_hosts_keep_find_queries_and_selection_isolated(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- memory path not exercised
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window._lyra("Somente janela principal")
        other._lyra("Somente outra janela")
        window.transcript_find.setText("principal")
        window.transcript_find_next.click()
        assert window.chat.textCursor().selectedText() == "principal"
        assert other.transcript_find.text() == ""
        assert other.chat.textCursor().selectedText() == ""
        assert other.transcript_find_status.text() == "Busca: pronta"
    finally:
        other.close()
