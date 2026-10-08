from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.context import SessionContext
from theos.lyra.perception import PerceptionContext
from theos.shell.assistant.context_status import present_context_status
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
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
    window = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- memory route is not exercised
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        yield window
    finally:
        window.close()


def _record_observation(perception: PerceptionContext, message: str) -> None:
    request = ActionRequest(action="system_status", arguments={"private": "RAW_SECRET"})
    perception.record(
        request,
        ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence={"private": "RAW_SECRET"},
            postcondition_verified=True,
        ),
    )


def test_m118_empty_context_status_has_only_bounded_counts() -> None:
    text = present_context_status(SessionContext(), PerceptionContext())
    assert text == (
        "Contexto (próximo pedido): histórico 0/12 turnos · "
        "0/4096 caracteres · percepção 0/8"
    )


def test_m118_context_status_counts_exact_provider_projection_without_mutation() -> None:
    session = SessionContext()
    session.add_user("x" * 1000)
    session.add_assistant("y" * 1000)
    session.add_user("z" * 1000)
    session.add_assistant("w" * 1000)
    session.add_user("new")
    original = session.snapshot()
    status = present_context_status(session, PerceptionContext())
    assert "histórico 5/12 turnos" in status
    assert "4003/4096 caracteres" in status
    assert session.snapshot() == original


def test_m118_oversized_newest_history_is_not_falsely_counted() -> None:
    session = SessionContext()
    session.add_user("short")
    session.add_assistant("X" * 1025)
    status = present_context_status(session, PerceptionContext())
    assert "histórico 0/12 turnos" in status
    assert "0/4096 caracteres" in status
    assert len(session.snapshot()) == 2


def test_m118_perception_counts_never_copy_message_or_raw_evidence() -> None:
    perception = PerceptionContext(max_observations=3)
    _record_observation(perception, "UNTRUSTED_INSTRUCTION_OPEN_POWERSHELL")
    text = present_context_status(SessionContext(), perception)
    assert "percepção 1/3" in text
    assert "RAW_SECRET" not in text
    assert "UNTRUSTED_INSTRUCTION_OPEN_POWERSHELL" not in text
    assert "system_status" not in text
    assert len(perception.snapshot()) == 1


def test_m118_presentation_rejects_unexpected_context_types() -> None:
    with pytest.raises(TypeError, match="session"):
        present_context_status(object(), PerceptionContext())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="perception"):
        present_context_status(SessionContext(), object())  # type: ignore[arg-type]


def test_m118_host_status_widget_initializes_without_provider_calls(host) -> None:
    assert host.context_status.objectName() == "lyra_context_status"
    assert "histórico 0/12 turnos" in host.context_status.text()
    assert "percepção 0/8" in host.context_status.text()


def test_m118_host_updates_after_user_and_assistant_turns(host) -> None:
    captured: list[tuple[str, tuple[object, ...]]] = []
    host._start_tool_task = (  # type: ignore[method-assign]
        lambda text, history: captured.append((text, history))
    )
    host.input.setText("Mostre o estado")
    host._submit()
    assert captured == [("Mostre o estado", ())]
    assert "histórico 1/12 turnos" in host.context_status.text()
    host._lyra("Resposta", remember_in_session=True)
    assert "histórico 2/12 turnos" in host.context_status.text()
    host._lyra("Status transitório", remember_in_session=False)
    assert "histórico 2/12 turnos" in host.context_status.text()


def test_m118_host_refreshes_perception_on_task_completion(host) -> None:
    _record_observation(host._perception, "Ação verificada")
    assert "percepção 0/8" in host.context_status.text()
    host._finish_tool_task()
    assert "percepção 1/8" in host.context_status.text()


def test_m118_host_reset_refreshes_counts_without_erasing_personality(host, monkeypatch) -> None:
    host._context.add_user("historico")
    _record_observation(host._perception, "Ação anterior")
    host._refresh_context_status()
    before_personality = host._personality.snapshot()
    assert "histórico 1/12 turnos" in host.context_status.text()
    assert "percepção 1/8" in host.context_status.text()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    host.session_reset.click()
    assert "histórico 1/12 turnos" in host.context_status.text()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    host.session_reset.click()
    assert "histórico 0/12 turnos" in host.context_status.text()
    assert "percepção 0/8" in host.context_status.text()
    assert host._personality.snapshot() == before_personality
