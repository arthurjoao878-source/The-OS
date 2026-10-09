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


def test_m125_label_starts_neutral_and_has_exact_object_name(host) -> None:
    window, provider, _ = host
    assert window.transcript_match_count.objectName() == "lyra_transcript_match_count"
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.chat.isReadOnly()
    assert provider.calls == 0


def test_m125_count_one_literal_match(host) -> None:
    window, _, _ = host
    window._lyra("Marcador_Incomum_125")
    window.transcript_find.setText("Marcador_Incomum_125")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.transcript_find_status.text() == "Busca: resultado selecionado"


def test_m125_case_insensitive_count_uses_qt_document_find(host) -> None:
    window, _, _ = host
    window._lyra("Banana BANANA banana")
    window.transcript_find.setText("banana")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 3"


def test_m125_literal_metacharacters_do_not_act_as_regex(host) -> None:
    window, _, _ = host
    window._lyra("a.b e axb")
    window.transcript_find.setText("a.b")
    window.transcript_find_previous.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"


def test_m125_no_matches_and_empty_query_have_neutral_status(host) -> None:
    window, _, _ = host
    window.transcript_find.setText("nunca_aparece_m125")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 0"
    window.transcript_find.clear()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    window.transcript_find_previous.click()
    assert window.transcript_find_status.text() == "Busca: informe termo"
    assert window.transcript_match_count.text() == "Ocorrências: —"


def test_m125_more_than_256_matches_is_bounded(host) -> None:
    window, _, _ = host
    window._lyra(" ".join(["token_m125"] * 280))
    window.transcript_find.setText("token_m125")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"


def test_m125_conversation_over_65536_is_not_scanned(host) -> None:
    window, _, _ = host
    window.chat.setPlainText("A" * 65537)
    window.transcript_find.setText("A")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_find_status.text() == "Busca: conversa acima do limite"


def test_m125_count_is_passive_no_provider_memory_or_draft_mutation(host) -> None:
    window, provider, memory_marker = host
    window._lyra("Palavra especial encontrada")
    window.input.setText("Rascunho privado")
    context = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    visible = window.chat.toPlainText()
    window.transcript_find.setText("Palavra")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window._context.snapshot() == context
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory_marker
    assert window.chat.toPlainText() == visible
    assert window.input.text() == "Rascunho privado"
    assert provider.calls == 0


def test_m125_busy_find_disabled_and_direct_handler_does_nothing(host) -> None:
    window, provider, _ = host
    window._lyra("Termo disponivel")
    window.transcript_find.setText("Termo")
    window._set_busy(True)
    try:
        assert not window.transcript_find.isEnabled()
        assert not window.transcript_find_next.isEnabled()
        window._find_next_in_transcript()
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)


def test_m125_denied_reset_preserves_count(host, monkeypatch) -> None:
    window, _, _ = host
    window._lyra("Termo")
    window.transcript_find.setText("Termo")
    window.transcript_find_next.click()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "Termo"
    assert window.transcript_match_count.text() == "Ocorrências: 1"


def test_m125_approved_reset_returns_to_neutral(host, monkeypatch) -> None:
    window, provider, _ = host
    window._lyra("Termo")
    window.transcript_find.setText("Termo")
    window.transcript_find_next.click()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window._context.snapshot() == ()
    assert provider.calls == 0


def test_m125_independent_host_count_state(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory route
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window._lyra("Uma")
        window.transcript_find.setText("Uma")
        window.transcript_find_next.click()
        assert window.transcript_match_count.text() == "Ocorrências: 1"
        assert other.transcript_match_count.text() == "Ocorrências: —"
        other._lyra("Outro outro")
        other.transcript_find.setText("outro")
        other.transcript_find_next.click()
        assert other.transcript_match_count.text() == "Ocorrências: 2"
        assert window.transcript_match_count.text() == "Ocorrências: 1"
    finally:
        other.close()
