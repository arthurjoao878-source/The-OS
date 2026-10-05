from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.lyra.execution import LyraRunState, ToolLoopResult
from theos.lyra.execution.composed_workflow import WorkflowDomain
from theos.lyra.execution.file_workflow import FileWorkflowPhase
from theos.lyra.execution.workflow_progress import (
    WORKFLOW_PROGRESS_VERSION,
    WorkflowProgressKind,
    summarize_workflow_progress,
)


def _record(
    state: LyraRunState,
    *,
    action: str,
    evidence: dict[str, object] | None = None,
    success: bool = True,
    error_code: str | None = None,
) -> LyraRunState:
    request = ActionRequest(action=action)
    result = ActionResult(
        request_id=request.request_id,
        success=success,
        message=f"{action} result",
        evidence=evidence or {},
        error_code=error_code,
    )
    return state.begin_action(request).record_action(request, result)


def test_new_run_has_started_progress() -> None:
    state = LyraRunState.start("Faça algo.", max_steps=4)

    progress = summarize_workflow_progress(state)

    assert progress.version == WORKFLOW_PROGRESS_VERSION == 1
    assert progress.kind is WorkflowProgressKind.STARTED
    assert progress.completed_steps == 0
    assert progress.remaining_steps == 4
    assert progress.current_action is None
    assert progress.domain_sequence == ()


def test_current_action_reports_running_domain() -> None:
    state = LyraRunState.start("Leia o arquivo.", max_steps=4)
    request = ActionRequest(action="read_text_file")
    state = state.begin_action(request)

    progress = summarize_workflow_progress(state)

    assert progress.kind is WorkflowProgressKind.ACTION_RUNNING
    assert progress.current_action == "read_text_file"
    assert progress.current_domain is WorkflowDomain.FILE
    assert progress.domain_sequence == (WorkflowDomain.FILE,)


def test_confirmation_pending_is_distinct_progress_kind() -> None:
    state = LyraRunState.start("Abra um aplicativo.", max_steps=4)
    request = ActionRequest(action="open_application")
    state = state.wait_for_confirmation(request)

    progress = summarize_workflow_progress(state)

    assert progress.kind is WorkflowProgressKind.AWAITING_CONFIRMATION
    assert progress.current_action == "open_application"
    assert progress.current_domain is WorkflowDomain.APPLICATION
    assert progress.completed_steps == 0


def test_completed_step_exposes_latest_step_and_file_phase() -> None:
    state = LyraRunState.start("Leia o arquivo.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )

    progress = summarize_workflow_progress(state)

    assert progress.kind is WorkflowProgressKind.STEP_COMPLETED
    assert progress.last_completed_action == "read_text_file"
    assert progress.last_completed_domain is WorkflowDomain.FILE
    assert progress.last_step_success is True
    assert progress.file_phase is FileWorkflowPhase.OBSERVED
    assert progress.completed_steps == 1
    assert progress.remaining_steps == 3


def test_pending_second_domain_is_visible_in_progress_sequence() -> None:
    state = LyraRunState.start("Leia e confira o sistema.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    request = ActionRequest(action="system_status")
    state = state.begin_action(request)

    progress = summarize_workflow_progress(state)

    assert progress.kind is WorkflowProgressKind.ACTION_RUNNING
    assert progress.domain_sequence == (
        WorkflowDomain.FILE,
        WorkflowDomain.SYSTEM,
    )
    assert progress.domain_count == 2
    assert progress.transition_count == 1
    assert progress.is_cross_domain is True


def test_terminal_completed_progress_preserves_last_evidence_context() -> None:
    state = LyraRunState.start("Confira o sistema.", max_steps=4)
    state = _record(
        state,
        action="system_status",
        evidence={"cpu_percent": 10.0},
    ).complete("Concluído.")

    progress = summarize_workflow_progress(state)

    assert progress.kind is WorkflowProgressKind.COMPLETED
    assert progress.current_action is None
    assert progress.last_completed_action == "system_status"
    assert progress.last_completed_domain is WorkflowDomain.SYSTEM
    assert progress.last_step_success is True


def test_failed_and_cancelled_terminal_states_are_distinguished() -> None:
    failed = LyraRunState.start("Finalize um processo.", max_steps=4)
    failed = _record(
        failed,
        action="terminate_process",
        success=False,
        error_code="PROCESS_TERMINATION_FAILED",
    ).fail("Falhou.")

    failed_progress = summarize_workflow_progress(failed)

    assert failed_progress.kind is WorkflowProgressKind.FAILED
    assert failed_progress.last_step_success is False
    assert failed_progress.latest_error_code == "PROCESS_TERMINATION_FAILED"

    cancelled = LyraRunState.start("Leia algo.", max_steps=4).cancel(
        "Cancelado."
    )
    cancelled_progress = summarize_workflow_progress(cancelled)

    assert cancelled_progress.kind is WorkflowProgressKind.CANCELLED
    assert cancelled_progress.completed_steps == 0


def test_tool_loop_result_exposes_progress_without_authority_claims() -> None:
    state = LyraRunState.start("Leia e confira o sistema.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    state = _record(
        state,
        action="system_status",
        evidence={"cpu_percent": 10.0},
    ).complete("Concluído.")

    result = ToolLoopResult(
        success=True,
        messages=(),
        final_reply="Concluído.",
        completed_steps=2,
        run_state=state,
    )

    progress = result.workflow_progress

    assert progress.kind is WorkflowProgressKind.COMPLETED
    assert progress.domain_sequence == (
        WorkflowDomain.FILE,
        WorkflowDomain.SYSTEM,
    )
    assert progress.file_phase is FileWorkflowPhase.OBSERVED
    assert not hasattr(progress, "goal_achieved")
    assert not hasattr(progress, "authorized")
