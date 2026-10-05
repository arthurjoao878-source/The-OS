from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from theos.lyra.execution.composed_workflow import (
    WorkflowDomain,
    workflow_domain_for_action,
)
from theos.lyra.execution.file_workflow import (
    FileWorkflowPhase,
    summarize_file_workflow,
)
from theos.lyra.execution.run_state import LyraRunState, RunStatus

WORKFLOW_PROGRESS_VERSION = 1


class WorkflowProgressKind(StrEnum):
    STARTED = "STARTED"
    ACTION_RUNNING = "ACTION_RUNNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    STEP_COMPLETED = "STEP_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class WorkflowProgressState:
    run_id: UUID
    kind: WorkflowProgressKind
    status: RunStatus
    completed_steps: int
    max_steps: int
    remaining_steps: int
    current_action: str | None
    current_domain: WorkflowDomain | None
    last_completed_action: str | None
    last_completed_domain: WorkflowDomain | None
    last_step_success: bool | None
    latest_error_code: str | None
    domain_sequence: tuple[WorkflowDomain, ...]
    file_phase: FileWorkflowPhase | None
    version: int = WORKFLOW_PROGRESS_VERSION

    def __post_init__(self) -> None:
        if self.version != WORKFLOW_PROGRESS_VERSION:
            raise ValueError("unsupported workflow progress version")
        if self.completed_steps < 0:
            raise ValueError("completed_steps must not be negative")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.completed_steps > self.max_steps:
            raise ValueError("completed_steps cannot exceed max_steps")
        if self.remaining_steps != self.max_steps - self.completed_steps:
            raise ValueError("remaining_steps do not match step budget")

        has_current_action = self.current_action is not None
        has_current_domain = self.current_domain is not None
        if has_current_action != has_current_domain:
            raise ValueError(
                "current_action and current_domain must be set together"
            )

        has_last_action = self.last_completed_action is not None
        has_last_domain = self.last_completed_domain is not None
        if has_last_action != has_last_domain:
            raise ValueError(
                "last_completed_action and last_completed_domain must be set together"
            )
        if self.completed_steps == 0 and (
            has_last_action
            or self.last_step_success is not None
            or self.latest_error_code is not None
        ):
            raise ValueError("empty progress cannot contain completed-step details")

    @property
    def domain_count(self) -> int:
        return len(dict.fromkeys(self.domain_sequence))

    @property
    def transition_count(self) -> int:
        return max(0, len(self.domain_sequence) - 1)

    @property
    def is_cross_domain(self) -> bool:
        return self.domain_count >= 2


def _progress_kind(run_state: LyraRunState) -> WorkflowProgressKind:
    if run_state.status is RunStatus.AWAITING_CONFIRMATION:
        return WorkflowProgressKind.AWAITING_CONFIRMATION
    if run_state.status is RunStatus.COMPLETED:
        return WorkflowProgressKind.COMPLETED
    if run_state.status is RunStatus.FAILED:
        return WorkflowProgressKind.FAILED
    if run_state.status is RunStatus.CANCELLED:
        return WorkflowProgressKind.CANCELLED
    if run_state.current_action is not None:
        return WorkflowProgressKind.ACTION_RUNNING
    if run_state.steps:
        return WorkflowProgressKind.STEP_COMPLETED
    return WorkflowProgressKind.STARTED


def _domain_sequence(
    run_state: LyraRunState,
) -> tuple[WorkflowDomain, ...]:
    sequence: list[WorkflowDomain] = []

    for step in run_state.steps:
        domain = workflow_domain_for_action(step.action)
        if not sequence or sequence[-1] is not domain:
            sequence.append(domain)

    if run_state.current_action is not None:
        current = workflow_domain_for_action(run_state.current_action)
        if not sequence or sequence[-1] is not current:
            sequence.append(current)

    return tuple(sequence)


def summarize_workflow_progress(
    run_state: LyraRunState,
) -> WorkflowProgressState:
    last_step = run_state.steps[-1] if run_state.steps else None
    file_workflow = summarize_file_workflow(run_state)

    current_action = run_state.current_action
    current_domain = (
        workflow_domain_for_action(current_action)
        if current_action is not None
        else None
    )

    last_completed_action = (
        last_step.action
        if last_step is not None
        else None
    )
    last_completed_domain = (
        workflow_domain_for_action(last_step.action)
        if last_step is not None
        else None
    )

    return WorkflowProgressState(
        run_id=run_state.run_id,
        kind=_progress_kind(run_state),
        status=run_state.status,
        completed_steps=run_state.completed_steps,
        max_steps=run_state.max_steps,
        remaining_steps=run_state.remaining_step_budget,
        current_action=current_action,
        current_domain=current_domain,
        last_completed_action=last_completed_action,
        last_completed_domain=last_completed_domain,
        last_step_success=(
            last_step.success
            if last_step is not None
            else None
        ),
        latest_error_code=(
            last_step.error_code
            if last_step is not None
            else None
        ),
        domain_sequence=_domain_sequence(run_state),
        file_phase=(
            file_workflow.phase
            if file_workflow is not None
            else None
        ),
    )
