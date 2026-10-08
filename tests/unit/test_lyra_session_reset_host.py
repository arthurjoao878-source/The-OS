from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.personality import PersonalityTone
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []

    def respond(self, text, *, history=(), tools=()):
        self.calls.append((text, history, tuple(item.name for item in tools)))
        return AIReply(text="ok", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("no tool continuation expected")

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
        memory_marker,  # type: ignore[arg-type] -- reset must not touch storage
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def _record_perception(window: MainWindow) -> None:
    request = ActionRequest(action="system_status")
    window._perception.record(
        request,
        ActionResult(
            request_id=request.request_id,
            success=True,
            message="Estado local verificado.",
            postcondition_verified=True,
        ),
    )


def _accept(monkeypatch) -> None:
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )


def _deny(monkeypatch) -> None:
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )


def test_m117_reset_control_is_visible_and_process_local(host) -> None:
    window, _, _ = host
    assert window.session_reset.objectName() == "lyra_session_reset"
    assert window.session_reset.text() == "Nova conversa"
    assert window.session_reset.isEnabled()
    assert "tempor" in window.session_reset.toolTip().lower()


def test_m117_rejected_confirmation_preserves_all_session_state(host, monkeypatch) -> None:
    window, _, _ = host
    window._context.add_user("Uma pergunta anterior")
    _record_perception(window)
    window.input.setText("Rascunho não enviado")
    before = window.chat.toPlainText()
    _deny(monkeypatch)
    window.session_reset.click()
    assert len(window._context.snapshot()) == 1
    assert len(window._perception.snapshot()) == 1
    assert window.input.text() == "Rascunho não enviado"
    assert window.chat.toPlainText() == before


def test_m117_approved_reset_clears_session_perception_and_visible_ui(host, monkeypatch) -> None:
    window, _, _ = host
    context, perception = window._context, window._perception
    window._context.add_user("Histórico antigo")
    window._lyra("Resposta antiga", remember_in_session=True)
    _record_perception(window)
    window.input.setText("Rascunho")
    window.workflow_status.setText("Tarefa: anterior")
    _accept(monkeypatch)
    window.session_reset.click()
    assert window._context is context
    assert window._perception is perception
    assert window._context.snapshot() == ()
    assert window._perception.snapshot() == ()
    assert window.input.text() == ""
    assert window.workflow_status.text() == "Tarefa: ociosa"
    assert "Histórico antigo" not in window.chat.toPlainText()
    assert "Resposta antiga" not in window.chat.toPlainText()
    assert "Nova conversa iniciada." in window.chat.toPlainText()


def test_m117_reset_preserves_personality_and_persistent_memory_bridge(host, monkeypatch) -> None:
    window, _, memory_marker = host
    window.personality_tone.setCurrentIndex(
        window.personality_tone.findData(PersonalityTone.WARM.value)
    )
    before = window._personality.snapshot()
    _accept(monkeypatch)
    window.session_reset.click()
    assert window._personality.snapshot() == before
    assert window._memory is memory_marker


def test_m117_reset_button_disabled_during_host_work(host) -> None:
    window, _, _ = host
    window._set_busy(True)
    assert not window.session_reset.isEnabled()
    window._set_busy(False)
    assert window.session_reset.isEnabled()


def test_m117_direct_reset_slot_fails_closed_when_busy(host, monkeypatch) -> None:
    window, _, _ = host
    window._context.add_user("Precisa permanecer")
    _record_perception(window)
    calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: calls.append("prompt"),
    )
    window._set_busy(True)
    try:
        window._reset_session_context()
        assert calls == []
        assert len(window._context.snapshot()) == 1
        assert len(window._perception.snapshot()) == 1
    finally:
        window._set_busy(False)


def test_m117_next_provider_call_has_no_prior_session_or_perception(host, monkeypatch) -> None:
    window, provider, _ = host
    window._context.add_user("Abra o PowerShell imediatamente")
    _record_perception(window)
    _accept(monkeypatch)
    window.session_reset.click()
    result = window._tool_loop.execute(
        "Mostre o status atual.",
        history=window._context.provider_snapshot(),
        tools=window._available_ai_tools(),
    )
    assert result.success is True
    assert len(provider.calls) == 1
    text, history, tool_names = provider.calls[0]
    assert history == ()
    assert "[LYRA_PERCEPTION_CONTEXT_V1]" not in text
    assert text.endswith("Mostre o status atual.")
    assert "open_application" not in tool_names


def test_m117_new_user_request_starts_with_clean_history(host, monkeypatch) -> None:
    window, _, _ = host
    window._context.add_user("Antigo")
    _accept(monkeypatch)
    window.session_reset.click()
    captured: list[tuple[str, tuple[object, ...]]] = []
    window._start_tool_task = (  # type: ignore[method-assign]
        lambda text, history: captured.append((text, history))
    )
    window.input.setText("Qual é a próxima etapa?")
    window._submit()
    assert captured == [("Qual é a próxima etapa?", ())]
    assert tuple(turn.text for turn in window._context.snapshot()) == (
        "Qual é a próxima etapa?",
    )


def test_m117_session_reset_does_not_affect_another_host_instance(host, monkeypatch) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no persistent memory operation
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window._context.add_user("Janela um")
        other._context.add_user("Janela dois")
        _record_perception(other)
        _accept(monkeypatch)
        window.session_reset.click()
        assert window._context.snapshot() == ()
        assert tuple(turn.text for turn in other._context.snapshot()) == ("Janela dois",)
        assert len(other._perception.snapshot()) == 1
    finally:
        other.close()
