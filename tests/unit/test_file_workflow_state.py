from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.integrations.ai.openai_responses import _SYSTEM_INSTRUCTIONS
from theos.lyra.execution import LyraRunState, RunStatus, ToolLoopResult
from theos.lyra.execution.file_workflow import (
    FILE_WORKFLOW_VERSION,
    FileWorkflowPhase,
    summarize_file_workflow,
)


def _record(
    state: LyraRunState,
    *,
    action: str,
    path: str | None = None,
    success: bool = True,
    write_verified: bool | None = None,
    sha256: str | None = None,
    error_code: str | None = None,
) -> LyraRunState:
    request = ActionRequest(action=action)
    evidence: dict[str, object] = {}
    if path is not None:
        evidence["path"] = path
    if write_verified is not None:
        evidence["write_verified"] = write_verified
    if sha256 is not None:
        evidence["sha256"] = sha256

    result = ActionResult(
        request_id=request.request_id,
        success=success,
        message=f"{action} result",
        evidence=evidence,
        error_code=error_code,
    )
    return state.begin_action(request).record_action(request, result)


def test_non_file_run_has_no_file_workflow_state() -> None:
    state = LyraRunState.start("Abra um aplicativo.", max_steps=4)
    state = _record(
        state,
        action="open_application",
        success=True,
    )

    assert summarize_file_workflow(state) is None


def test_read_only_text_file_workflow_is_observed() -> None:
    state = LyraRunState.start("Leia o arquivo.", max_steps=4)
    state = _record(
        state,
        action="read_text_file",
        path=r"C:\Temp\notes.txt",
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    assert workflow.version == FILE_WORKFLOW_VERSION == 1
    assert workflow.phase is FileWorkflowPhase.OBSERVED
    assert workflow.target_count == 1
    target = workflow.targets[0]
    assert target.observation_count == 1
    assert target.observed_before_mutation is True
    assert target.mutation_count == 0


def test_verified_write_is_structured_without_inventing_goal_success() -> None:
    state = LyraRunState.start("Crie o arquivo.", max_steps=4)
    state = _record(
        state,
        action="write_text_file",
        path=r"C:\Temp\notes.txt",
        write_verified=True,
        sha256="a" * 64,
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    assert workflow.phase is FileWorkflowPhase.VERIFIED
    assert workflow.mutation_count == 1
    assert workflow.verified_mutation_count == 1
    assert workflow.all_mutations_verified is True
    assert workflow.targets[0].latest_sha256 == "a" * 64
    assert not hasattr(workflow, "goal_achieved")


def test_observation_before_and_after_mutation_are_distinguished() -> None:
    state = LyraRunState.start("Leia, edite e confira.", max_steps=4)
    path = r"C:\Temp\notes.txt"
    state = _record(
        state,
        action="read_text_lines",
        path=path,
    )
    state = _record(
        state,
        action="replace_text_literal",
        path=path,
        write_verified=True,
        sha256="b" * 64,
    )
    state = _record(
        state,
        action="read_text_file",
        path=path,
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    target = workflow.targets[0]
    assert workflow.phase is FileWorkflowPhase.VERIFIED
    assert target.observed_before_mutation is True
    assert target.post_mutation_observation is True
    assert target.observation_count == 2
    assert target.mutation_actions == ("replace_text_literal",)


def test_successful_mutation_without_local_write_verification_is_unverified() -> None:
    state = LyraRunState.start("Edite o arquivo.", max_steps=4)
    state = _record(
        state,
        action="replace_text_block",
        path=r"C:\Temp\notes.txt",
        write_verified=False,
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    assert workflow.phase is FileWorkflowPhase.UNVERIFIED
    assert workflow.mutation_count == 1
    assert workflow.verified_mutation_count == 0
    assert workflow.all_mutations_verified is False


def test_failed_mutation_is_reported_as_failed_workflow() -> None:
    state = LyraRunState.start("Edite o arquivo.", max_steps=4)
    state = _record(
        state,
        action="replace_text_literal",
        path=r"C:\Temp\notes.txt",
        success=False,
        error_code="FILE_CHANGED_AFTER_PREVIEW",
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    assert workflow.phase is FileWorkflowPhase.FAILED
    assert workflow.failed_mutation_count == 1
    assert workflow.targets[0].latest_error_code == "FILE_CHANGED_AFTER_PREVIEW"


def test_multiple_file_targets_keep_independent_verified_evidence() -> None:
    state = LyraRunState.start("Atualize dois arquivos.", max_steps=4)
    state = _record(
        state,
        action="write_text_file",
        path=r"C:\Temp\A.txt",
        write_verified=True,
        sha256="c" * 64,
    )
    state = _record(
        state,
        action="replace_text_literal",
        path="c:/temp/b.txt",
        write_verified=True,
        sha256="d" * 64,
    )

    workflow = summarize_file_workflow(state)

    assert workflow is not None
    assert workflow.phase is FileWorkflowPhase.VERIFIED
    assert workflow.target_count == 2
    assert workflow.mutation_count == 2
    assert workflow.verified_mutation_count == 2
    assert [target.latest_sha256 for target in workflow.targets] == [
        "c" * 64,
        "d" * 64,
    ]


def test_tool_loop_result_exposes_file_workflow_and_provider_guidance() -> None:
    state = LyraRunState.start("Edite o arquivo.", max_steps=4)
    state = _record(
        state,
        action="write_text_file",
        path=r"C:\Temp\notes.txt",
        write_verified=True,
        sha256="e" * 64,
    ).complete("Arquivo atualizado.")

    result = ToolLoopResult(
        success=True,
        messages=(),
        final_reply="Arquivo atualizado.",
        completed_steps=1,
        run_state=state,
    )

    assert state.status is RunStatus.COMPLETED
    assert result.file_workflow is not None
    assert result.file_workflow.phase is FileWorkflowPhase.VERIFIED
    assert "read_text_file" in _SYSTEM_INSTRUCTIONS
    assert "replace_text_literal" in _SYSTEM_INSTRUCTIONS
    assert "write_verified" in _SYSTEM_INSTRUCTIONS
    assert "objetivo maior" in _SYSTEM_INSTRUCTIONS
