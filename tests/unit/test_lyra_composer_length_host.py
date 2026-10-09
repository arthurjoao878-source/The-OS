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
        memory_marker,  # type: ignore[arg-type] -- no memory route in these tests
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m123_limit_and_neutral_counter_are_initially_visible(host) -> None:
    window, provider, _ = host
    assert window.input.maxLength() == 4096
    assert window.composer_length_status.objectName() == "lyra_composer_length_status"
    assert window.composer_length_status.text() == "Mensagem: 0/4096"
    assert window.input.text() == ""
    assert provider.calls == 0


def test_m123_counter_updates_on_normal_edits(host) -> None:
    window, _, _ = host
    window.input.setText("abc")
    assert window.composer_length_status.text() == "Mensagem: 3/4096"
    window.input.setText("abc def")
    assert window.composer_length_status.text() == "Mensagem: 7/4096"
    window.input.clear()
    assert window.composer_length_status.text() == "Mensagem: 0/4096"


def test_m123_boundary_4096_and_overlength_programmatic_paste(host) -> None:
    window, _, _ = host
    window.input.setText("x" * 4096)
    assert len(window.input.text()) == 4096
    assert window.composer_length_status.text() == "Mensagem: 4096/4096"
    window.input.setText("y" * 4097)
    assert window.input.text() == "y" * 4096
    assert window.composer_length_status.text() == "Mensagem: 4096/4096"


def test_m123_nonascii_counter_shows_length_not_raw_text(host) -> None:
    window, provider, _ = host
    window.input.setText("ação segura")
    assert window.composer_length_status.text() == "Mensagem: 11/4096"
    assert "ação" not in window.composer_length_status.text()
    assert provider.calls == 0


def test_m123_draft_recall_updates_counter_without_auto_submit(host) -> None:
    window, provider, _ = host
    window._context.add_user("Pedido anterior")
    window.input.setText("novo rascunho")
    window.draft_previous.click()
    assert window.input.text() == "Pedido anterior"
    assert window.composer_length_status.text() == "Mensagem: 15/4096"
    window.draft_next.click()
    assert window.input.text() == "novo rascunho"
    assert window.composer_length_status.text() == "Mensagem: 13/4096"
    assert provider.calls == 0


def test_m123_reset_denied_preserves_composer_and_counter(host, monkeypatch) -> None:
    window, provider, _ = host
    window.input.setText("mensagem não enviada")
    before = window._context.snapshot()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.input.text() == "mensagem não enviada"
    assert window.composer_length_status.text() == "Mensagem: 20/4096"
    assert window._context.snapshot() == before
    assert provider.calls == 0


def test_m123_reset_accepted_clears_counter_and_temporary_context(
    host, monkeypatch
) -> None:
    window, provider, memory_marker = host
    window.input.setText("rascunho")
    window._context.add_user("pedido guardado")
    before_personality = window._personality.snapshot()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.input.text() == ""
    assert window.composer_length_status.text() == "Mensagem: 0/4096"
    assert window._context.snapshot() == ()
    assert window._personality.snapshot() == before_personality
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m123_busy_prevents_direct_submit_bypass(host) -> None:
    window, provider, _ = host
    window.input.setText("pedido ainda não enviado")
    before = window._context.snapshot()
    window._set_busy(True)
    try:
        assert not window.input.isEnabled()
        assert not window.send.isEnabled()
        window._submit()
        assert window._context.snapshot() == before
        assert window.input.text() == "pedido ainda não enviado"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.composer_length_status.text() == "Mensagem: 24/4096"


def test_m123_full_boundary_submit_uses_normal_host_path(host) -> None:
    window, provider, _ = host
    request = "z" * 4096
    captured: list[tuple[str, tuple[object, ...]]] = []
    window._start_tool_task = (  # type: ignore[method-assign]
        lambda text, history: captured.append((text, history))
    )
    window.input.setText(request)
    window.send.click()
    assert len(captured) == 1
    assert captured[0][0] == request
    assert window.input.text() == ""
    assert window.composer_length_status.text() == "Mensagem: 0/4096"
    assert provider.calls == 0


def test_m123_whitespace_does_not_submit(host) -> None:
    window, provider, _ = host
    window.input.setText("   ")
    before = window._context.snapshot()
    window.send.click()
    assert window.input.text() == "   "
    assert window.composer_length_status.text() == "Mensagem: 3/4096"
    assert window._context.snapshot() == before
    assert provider.calls == 0


def test_m123_counter_is_passive_and_does_not_change_other_contexts(host) -> None:
    window, provider, memory_marker = host
    before_session = window._context.snapshot()
    before_perception = window._perception.snapshot()
    before_personality = window._personality.snapshot()
    before_chat = window.chat.toPlainText()
    window.input.setText("PRIVADO")
    assert window.composer_length_status.text() == "Mensagem: 7/4096"
    assert "PRIVADO" not in window.composer_length_status.text()
    assert window._context.snapshot() == before_session
    assert window._perception.snapshot() == before_perception
    assert window._personality.snapshot() == before_personality
    assert window.chat.toPlainText() == before_chat
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m123_counter_isolated_between_windows_and_find_unmodified(host) -> None:
    window, provider, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory route in these tests
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window.input.setText("uma janela")
        other.input.setText("outra")
        assert window.composer_length_status.text() == "Mensagem: 10/4096"
        assert other.composer_length_status.text() == "Mensagem: 5/4096"
        window._lyra("termo para buscar")
        window.transcript_find.setText("termo")
        window.transcript_find_next.click()
        assert window.chat.textCursor().selectedText() == "termo"
        assert provider.calls == 0
    finally:
        other.close()
