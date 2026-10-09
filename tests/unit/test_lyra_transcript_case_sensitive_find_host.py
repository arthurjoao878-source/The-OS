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


def test_m127_default_off_and_neutral_labels(host) -> None:
    window, provider, _ = host
    assert (
        window.transcript_find_case_sensitive.objectName()
        == "lyra_transcript_find_case_sensitive"
    )
    assert not window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert provider.calls == 0


def test_m127_default_insensitive_count_and_rank(host) -> None:
    window, _, _ = host
    window._lyra("Cedar cedar CEDAR")
    window.transcript_find.setText("cedar")
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert window.transcript_match_position.text() == "Posição: 1 de 3"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"


def test_m127_explicit_case_sensitive_filter(host) -> None:
    window, _, _ = host
    window._lyra("Cedar cedar CEDAR")
    window.transcript_find.setText("Cedar")
    window.transcript_find_case_sensitive.click()
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.transcript_match_position.text() == "Posição: 1 de 1"
    assert window.chat.textCursor().selectedText() == "Cedar"


def test_m127_sensitive_two_matches_ranked(host) -> None:
    window, _, _ = host
    window._lyra("AB ab AB aB")
    window.transcript_find.setText("AB")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m127_mode_toggle_invalidates_without_scanning(host, monkeypatch) -> None:
    window, provider, _ = host
    window._lyra("Quartz quartz")
    window.transcript_find.setText("quartz")
    window.transcript_find_next.click()
    original = window.chat.textCursor().selectedText()
    monkeypatch.setattr(
        window,
        "_update_transcript_match_count",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scan")),
    )
    window.transcript_find_case_sensitive.click()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window.chat.textCursor().selectedText() == original
    assert provider.calls == 0


def test_m127_previous_and_wrap_use_sensitive_results(host) -> None:
    window, _, _ = host
    window._lyra("Delta DELTA Delta")
    window.transcript_find.setText("Delta")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 1 de 2"
    window.transcript_find_previous.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 2"


def test_m127_case_sensitive_literal_not_regex(host) -> None:
    window, _, _ = host
    window._lyra("A.B a.b A-B")
    window.transcript_find.setText("A.B")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.chat.textCursor().selectedText() == "A.B"


def test_m127_case_sensitive_no_match_reports_zero(host) -> None:
    window, _, _ = host
    window._lyra("onlylower")
    window.transcript_find.setText("ONLYLOWER")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 0"
    assert window.transcript_match_position.text() == "Posição: —"


def test_m127_bounded_count_and_rank_remain_consistent(host) -> None:
    window, _, _ = host
    window._lyra(" ".join(["M127CAP"] * 260) + " m127cap")
    window.transcript_find.setText("M127CAP")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: 1 de 256+"
    window._last_find_query = "M127CAP"
    cursor = window.chat.textCursor()
    cursor.setPosition(window.chat.toPlainText().rfind("M127CAP") - 1)
    window.chat.setTextCursor(cursor)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 256+"
    assert window.transcript_match_position.text() == "Posição: >256 de 256+"


def test_m127_query_ceiling_still_fail_closed(host) -> None:
    window, _, _ = host
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find.setMaxLength(200)
    window.transcript_find.setText("X" * 121)
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"
    assert window.transcript_find_status.text() == "Busca: termo acima do limite"


def test_m127_transcript_ceiling_still_fail_closed(host) -> None:
    window, _, _ = host
    window.chat.setPlainText("M" * 65537)
    window.transcript_find.setText("M")
    window.transcript_find_case_sensitive.setChecked(True)
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: indisponível"
    assert window.transcript_match_position.text() == "Posição: indisponível"
    assert window.transcript_find_status.text() == "Busca: conversa acima do limite"


def test_m127_busy_mode_disabled_and_find_guarded(host) -> None:
    window, provider, _ = host
    window._lyra("Busy")
    window.transcript_find.setText("Busy")
    window._set_busy(True)
    try:
        assert not window.transcript_find_case_sensitive.isEnabled()
        window._find_next_in_transcript()
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert window.transcript_match_position.text() == "Posição: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_case_sensitive.isEnabled()


def test_m127_denied_reset_preserves_mode_and_count(host, monkeypatch) -> None:
    window, _, _ = host
    window._lyra("Rst rst")
    window.transcript_find.setText("Rst")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert window.transcript_match_position.text() == "Posição: 1 de 1"


def test_m127_confirmed_reset_restores_default_isolated(host, monkeypatch) -> None:
    window, provider, _ = host
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        CaptureProvider(), build_default_tool_catalog(),
    )
    try:
        window.transcript_find_case_sensitive.setChecked(True)
        other.transcript_find_case_sensitive.setChecked(True)
        window._lyra("Reset")
        window.transcript_find.setText("Reset")
        window.transcript_find_next.click()
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )
        window.session_reset.click()
        assert not window.transcript_find_case_sensitive.isChecked()
        assert window.transcript_find.text() == ""
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert window.transcript_match_position.text() == "Posição: —"
        assert other.transcript_find_case_sensitive.isChecked()
        assert provider.calls == 0
    finally:
        other.close()


def test_m127_passive_mode_preserves_context_memory_and_draft(host) -> None:
    window, provider, memory_marker = host
    window._lyra("Same same Same")
    window.input.setText("rascunho privado")
    snapshot = window._context.snapshot()
    perception = window._perception.snapshot()
    personality = window._personality.snapshot()
    visible = window.chat.toPlainText()
    window.transcript_find.setText("Same")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_next.click()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window._context.snapshot() == snapshot
    assert window._perception.snapshot() == perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory_marker
    assert window.input.text() == "rascunho privado"
    assert window.chat.toPlainText() == visible
    assert provider.calls == 0
