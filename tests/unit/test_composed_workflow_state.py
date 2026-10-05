from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.integrations.ai.openai_responses import _SYSTEM_INSTRUCTIONS
from theos.lyra.execution import LyraRunState, RunStatus, ToolLoopResult
from theos.lyra.execution.composed_workflow import (
    COMPOSED_WORKFLOW_VERSION,
    WorkflowDomain,
    summarize_composed_workflow,
    workflow_domain_for_action,
)
from theos.lyra.execution.file_workflow import FileWorkflowPhase


def _record(
    state: LyraRunState,
    *,
    action: str,
    evidence: dict[str, object] | None = None,
    success: bool = True,
    effect_dispatched: bool | None = None,
    postcondition_verified: bool | None = None,
    error_code: str | None = None,
) -> LyraRunState:
    request = ActionRequest(action=action)
    result = ActionResult(
        request_id=request.request_id,
        success=success,
        message=f"{action} result",
        evidence=evidence or {},
        error_code=error_code,
        effect_dispatched=effect_dispatched,
        postcondition_verified=postcondition_verified,
    )
    return state.begin_action(request).record_action(request, result)


def test_single_domain_run_has_no_composed_workflow() -> None:
    state = LyraRunState.start("Leia e edite o arquivo.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    state = _record(
        state,
        action="replace_text_literal",
        evidence={
            "path": r"C:\Temp\notes.txt",
            "write_verified": True,
        },
    )

    assert summarize_composed_workflow(state) is None


def test_cross_domain_steps_form_ordered_stages() -> None:
    state = LyraRunState.start("Leia o arquivo e maximize a janela.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    state = _record(
        state,
        action="maximize_window",
        evidence={"title": "Notas"},
        effect_dispatched=True,
        postcondition_verified=True,
    )

    workflow = summarize_composed_workflow(state)

    assert workflow is not None
    assert workflow.version == COMPOSED_WORKFLOW_VERSION == 1
    assert workflow.run_id == state.run_id
    assert workflow.domain_sequence == (
        WorkflowDomain.FILE,
        WorkflowDomain.WINDOW,
    )
    assert workflow.domains == (
        WorkflowDomain.FILE,
        WorkflowDomain.WINDOW,
    )
    assert workflow.domain_count == 2
    assert workflow.transition_count == 1
    assert workflow.step_count == 2
    assert workflow.effect_dispatched_count == 1
    assert workflow.postcondition_verified_count == 1


def test_contiguous_actions_in_same_domain_share_one_stage() -> None:
    state = LyraRunState.start("Organize a janela e leia o arquivo.", max_steps=4)
    state = _record(state, action="window_snapshot", evidence={"windows": []})
    state = _record(
        state,
        action="maximize_window",
        evidence={"title": "Notas"},
        postcondition_verified=True,
    )
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )

    workflow = summarize_composed_workflow(state)

    assert workflow is not None
    assert len(workflow.stages) == 2
    assert workflow.stages[0].domain is WorkflowDomain.WINDOW
    assert workflow.stages[0].actions == (
        "window_snapshot",
        "maximize_window",
    )
    assert workflow.stages[0].start_step == 1
    assert workflow.stages[0].end_step == 2
    assert workflow.stages[1].domain is WorkflowDomain.FILE
    assert workflow.transition_count == 1


def test_pending_second_domain_is_visible_before_execution() -> None:
    state = LyraRunState.start("Leia e depois abra um aplicativo.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    pending = ActionRequest(
        action="open_application",
        arguments={"application": "Notepad"},
    )
    state = state.wait_for_confirmation(pending)

    workflow = summarize_composed_workflow(state)

    assert workflow is not None
    assert workflow.status is RunStatus.AWAITING_CONFIRMATION
    assert workflow.current_action == "open_application"
    assert workflow.current_domain is WorkflowDomain.APPLICATION
    assert workflow.domain_sequence == (
        WorkflowDomain.FILE,
        WorkflowDomain.APPLICATION,
    )
    assert workflow.step_count == 1
    assert workflow.run_id == state.run_id


def test_file_workflow_is_composed_without_duplicating_evidence() -> None:
    path = r"C:\Temp\notes.txt"
    state = LyraRunState.start("Edite o arquivo e veja a janela.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": path},
    )
    state = _record(
        state,
        action="replace_text_literal",
        evidence={
            "path": path,
            "write_verified": True,
            "sha256": "a" * 64,
        },
    )
    state = _record(
        state,
        action="window_snapshot",
        evidence={"windows": []},
    )

    workflow = summarize_composed_workflow(state)

    assert workflow is not None
    assert workflow.file_workflow is not None
    assert workflow.file_workflow.phase is FileWorkflowPhase.VERIFIED
    assert workflow.file_workflow.verified_mutation_count == 1
    assert workflow.file_workflow.targets[0].latest_sha256 == "a" * 64
    assert not hasattr(workflow, "goal_achieved")


def test_failed_step_is_counted_without_claiming_goal_failure_semantics() -> None:
    state = LyraRunState.start("Leia o arquivo e finalize o processo.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    state = _record(
        state,
        action="terminate_process",
        success=False,
        error_code="PROCESS_TERMINATION_FAILED",
    ).fail("A ação de processo falhou.")

    workflow = summarize_composed_workflow(state)

    assert workflow is not None
    assert workflow.status is RunStatus.FAILED
    assert workflow.failed_step_count == 1
    assert workflow.successful_step_count == 1
    assert workflow.stages[-1].success is False
    assert not hasattr(workflow, "goal_achieved")


def test_domain_classifier_keeps_development_separate_from_runtime_domains() -> None:
    assert workflow_domain_for_action("open_application") is WorkflowDomain.APPLICATION
    assert workflow_domain_for_action("read_text_file") is WorkflowDomain.FILE
    assert workflow_domain_for_action("window_snapshot") is WorkflowDomain.WINDOW
    assert workflow_domain_for_action("process_snapshot") is WorkflowDomain.PROCESS
    assert workflow_domain_for_action("system_status") is WorkflowDomain.SYSTEM
    assert workflow_domain_for_action("git_status_snapshot") is WorkflowDomain.DEVELOPMENT
    assert workflow_domain_for_action("future_tool") is WorkflowDomain.OTHER


def test_tool_loop_result_exposes_composed_workflow_and_provider_guidance() -> None:
    state = LyraRunState.start("Leia e inspecione a janela.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        evidence={"path": r"C:\Temp\notes.txt"},
    )
    state = _record(
        state,
        action="window_snapshot",
        evidence={"windows": []},
    ).complete("Fluxo concluído.")

    result = ToolLoopResult(
        success=True,
        messages=(),
        final_reply="Fluxo concluído.",
        completed_steps=2,
        run_state=state,
    )

    assert result.composed_workflow is not None
    assert result.composed_workflow.is_cross_domain is True
    assert "pedidos compostos" in _SYSTEM_INSTRUCTIONS
    assert "evidência retornada" in _SYSTEM_INSTRUCTIONS
    assert "objetivo geral" in _SYSTEM_INSTRUCTIONS
