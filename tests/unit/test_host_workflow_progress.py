from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.workflow_progress import (
    HOST_WORKFLOW_PROGRESS_VERSION,
    present_run_state,
)


def _record(
    state: LyraRunState,
    *,
    action: str,
    success: bool = True,
    error_code: str | None = None,
) -> LyraRunState:
    request = ActionRequest(action=action)
    result = ActionResult(
        request_id=request.request_id,
        success=success,
        message=f"{action} result",
        error_code=error_code,
    )
    return state.begin_action(request).record_action(request, result)


def test_host_progress_started_view() -> None:
    state = LyraRunState.start("Faça algo.", max_steps=4)

    view = present_run_state(state)

    assert view.version == HOST_WORKFLOW_PROGRESS_VERSION == 1
    assert view.text == "Tarefa: iniciada · 0/4 etapas"
    assert view.terminal is False


def test_host_progress_running_view_uses_current_domain() -> None:
    state = LyraRunState.start("Leia o arquivo.", max_steps=4)
    state = state.begin_action(ActionRequest(action="read_text_file"))

    view = present_run_state(state)

    assert view.text == (
        "Tarefa: executando read_text_file · arquivo · 0/4 etapas"
    )
    assert view.terminal is False


def test_host_progress_confirmation_view_is_distinct() -> None:
    state = LyraRunState.start("Abra o aplicativo.", max_steps=4)
    state = state.wait_for_confirmation(
        ActionRequest(action="open_application")
    )

    view = present_run_state(state)

    assert view.text == (
        "Tarefa: aguardando confirmação · open_application · "
        "aplicativo · 0/4 etapas"
    )
    assert view.terminal is False


def test_host_progress_step_completed_view_uses_latest_action() -> None:
    state = LyraRunState.start("Confira o sistema.", max_steps=4)
    state = _record(state, action="system_status")

    view = present_run_state(state)

    assert view.text == (
        "Tarefa: etapa 1/4 concluída · system_status · sistema"
    )
    assert view.terminal is False


def test_host_progress_completed_view_is_terminal() -> None:
    state = LyraRunState.start("Confira o sistema.", max_steps=4)
    state = _record(state, action="system_status").complete("Concluído.")

    view = present_run_state(state)

    assert view.text == "Tarefa: concluída · 1/4 etapas · sistema"
    assert view.terminal is True


def test_host_progress_failed_view_is_terminal() -> None:
    state = LyraRunState.start("Finalize o processo.", max_steps=4)
    state = _record(
        state,
        action="terminate_process",
        success=False,
        error_code="PROCESS_TERMINATION_FAILED",
    ).fail("Falhou.")

    view = present_run_state(state)

    assert view.text == "Tarefa: falhou · 1/4 etapas · processo"
    assert view.terminal is True


def test_host_progress_cancelled_view_is_terminal() -> None:
    state = LyraRunState.start("Faça algo.", max_steps=4).cancel(
        "Cancelado."
    )

    view = present_run_state(state)

    assert view.text == "Tarefa: cancelada · 0/4 etapas"
    assert view.terminal is True


def test_host_progress_cross_domain_running_view_tracks_current_action() -> None:
    state = LyraRunState.start(
        "Leia o arquivo e confira o sistema.",
        max_steps=4,
    )
    state = _record(state, action="read_text_file")
    state = state.begin_action(ActionRequest(action="system_status"))

    view = present_run_state(state)

    assert view.text == (
        "Tarefa: executando system_status · sistema · 1/4 etapas"
    )
    assert view.terminal is False
    assert not hasattr(view, "authorized")
    assert not hasattr(view, "goal_achieved")
