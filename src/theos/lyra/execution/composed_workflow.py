from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from theos.lyra.execution.file_workflow import (
    FileWorkflowState,
    summarize_file_workflow,
)
from theos.lyra.execution.run_state import LyraRunState, RunStatus, RunStepState

COMPOSED_WORKFLOW_VERSION = 1

_APPLICATION_ACTIONS = frozenset(
    {
        "open_application",
    }
)

_FILE_ACTIONS = frozenset(
    {
        "inspect_path",
        "find_path",
        "search_text",
        "open_path",
        "read_text_file",
        "read_text_lines",
        "write_text_file",
        "replace_text_literal",
        "replace_text_block",
        "create_directory",
        "copy_path",
        "move_path",
        "trash_path",
    }
)

_WINDOW_ACTIONS = frozenset(
    {
        "window_snapshot",
        "window_snapshot_many",
        "semantic_window_snapshot",
        "invoke_semantic_button",
        "set_semantic_checkbox_state",
        "set_semantic_text",
        "activate_window",
        "move_cursor_window_anchor",
        "click_window",
        "click_window_anchor",
        "double_click_window",
        "double_click_window_anchor",
        "drag_window_anchor",
        "scroll_window_anchor",
        "scroll_window",
        "press_key",
        "press_shortcut",
        "type_text",
        "place_window",
        "place_window_pair",
        "place_window_set",
        "restore_window",
        "maximize_window",
        "minimize_window",
        "close_window",
    }
)

_PROCESS_ACTIONS = frozenset(
    {
        "process_snapshot",
        "terminate_process",
    }
)

_SYSTEM_ACTIONS = frozenset(
    {
        "system_status",
    }
)

_DEVELOPMENT_ACTIONS = frozenset(
    {
        "check_python_syntax",
        "check_python_static",
        "check_python_static_many",
        "run_python_unit_test_file",
        "run_python_unit_test_files",
        "git_commit_staged_new_file",
        "git_commit_staged_file",
        "git_diff_file",
        "git_stage_file",
        "git_stage_new_file",
        "git_unstage_new_file",
        "git_unstage_file",
        "git_fetch_remote_main",
        "git_remote_head_snapshot",
        "git_remote_identity_snapshot",
        "git_status_snapshot",
    }
)


class WorkflowDomain(StrEnum):
    APPLICATION = "APPLICATION"
    DEVELOPMENT = "DEVELOPMENT"
    FILE = "FILE"
    OTHER = "OTHER"
    PROCESS = "PROCESS"
    SYSTEM = "SYSTEM"
    WINDOW = "WINDOW"


def workflow_domain_for_action(action: str) -> WorkflowDomain:
    normalized = action.strip()
    if not normalized:
        raise ValueError("workflow action must not be blank")
    if normalized in _APPLICATION_ACTIONS:
        return WorkflowDomain.APPLICATION
    if normalized in _DEVELOPMENT_ACTIONS:
        return WorkflowDomain.DEVELOPMENT
    if normalized in _FILE_ACTIONS:
        return WorkflowDomain.FILE
    if normalized in _PROCESS_ACTIONS:
        return WorkflowDomain.PROCESS
    if normalized in _SYSTEM_ACTIONS:
        return WorkflowDomain.SYSTEM
    if normalized in _WINDOW_ACTIONS:
        return WorkflowDomain.WINDOW
    return WorkflowDomain.OTHER


@dataclass(frozen=True, slots=True)
class WorkflowStageState:
    index: int
    domain: WorkflowDomain
    start_step: int
    end_step: int
    actions: tuple[str, ...]
    successful_step_count: int
    failed_step_count: int
    evidence_step_count: int
    effect_dispatched_count: int
    postcondition_verified_count: int

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("workflow stage index must be positive")
        if self.start_step < 1 or self.end_step < self.start_step:
            raise ValueError("workflow stage step range is invalid")

        expected_count = self.end_step - self.start_step + 1
        if len(self.actions) != expected_count:
            raise ValueError("workflow stage actions do not match step range")
        if any(not action.strip() for action in self.actions):
            raise ValueError("workflow stage actions must not be blank")

        counts = (
            self.successful_step_count,
            self.failed_step_count,
            self.evidence_step_count,
            self.effect_dispatched_count,
            self.postcondition_verified_count,
        )
        if any(value < 0 or value > expected_count for value in counts):
            raise ValueError("workflow stage count is out of range")
        if self.successful_step_count + self.failed_step_count != expected_count:
            raise ValueError("workflow stage success counts do not match steps")

    @property
    def step_count(self) -> int:
        return len(self.actions)

    @property
    def success(self) -> bool:
        return self.failed_step_count == 0


@dataclass(frozen=True, slots=True)
class ComposedWorkflowState:
    run_id: UUID
    goal: str
    status: RunStatus
    stages: tuple[WorkflowStageState, ...]
    current_action: str | None
    current_domain: WorkflowDomain | None
    file_workflow: FileWorkflowState | None
    version: int = COMPOSED_WORKFLOW_VERSION

    def __post_init__(self) -> None:
        normalized_goal = self.goal.strip()
        if not normalized_goal:
            raise ValueError("composed workflow goal must not be blank")
        object.__setattr__(self, "goal", normalized_goal)

        if self.version != COMPOSED_WORKFLOW_VERSION:
            raise ValueError("unsupported composed workflow version")

        for expected_index, stage in enumerate(self.stages, start=1):
            if stage.index != expected_index:
                raise ValueError("workflow stage indexes must be contiguous")
            if expected_index > 1:
                previous = self.stages[expected_index - 2]
                if stage.start_step != previous.end_step + 1:
                    raise ValueError("workflow stage step ranges must be contiguous")
                if stage.domain is previous.domain:
                    raise ValueError("adjacent workflow stages must differ by domain")

        has_current_action = self.current_action is not None
        has_current_domain = self.current_domain is not None
        if has_current_action != has_current_domain:
            raise ValueError(
                "current_action and current_domain must be set together"
            )
        if self.current_action is not None and not self.current_action.strip():
            raise ValueError("current_action must not be blank")

    @property
    def step_count(self) -> int:
        return sum(stage.step_count for stage in self.stages)

    @property
    def successful_step_count(self) -> int:
        return sum(stage.successful_step_count for stage in self.stages)

    @property
    def failed_step_count(self) -> int:
        return sum(stage.failed_step_count for stage in self.stages)

    @property
    def evidence_step_count(self) -> int:
        return sum(stage.evidence_step_count for stage in self.stages)

    @property
    def effect_dispatched_count(self) -> int:
        return sum(stage.effect_dispatched_count for stage in self.stages)

    @property
    def postcondition_verified_count(self) -> int:
        return sum(
            stage.postcondition_verified_count
            for stage in self.stages
        )

    @property
    def domain_sequence(self) -> tuple[WorkflowDomain, ...]:
        sequence = [stage.domain for stage in self.stages]
        if (
            self.current_domain is not None
            and (not sequence or sequence[-1] is not self.current_domain)
        ):
            sequence.append(self.current_domain)
        return tuple(sequence)

    @property
    def domains(self) -> tuple[WorkflowDomain, ...]:
        ordered: list[WorkflowDomain] = []
        for domain in self.domain_sequence:
            if domain not in ordered:
                ordered.append(domain)
        return tuple(ordered)

    @property
    def domain_count(self) -> int:
        return len(self.domains)

    @property
    def transition_count(self) -> int:
        return max(0, len(self.domain_sequence) - 1)

    @property
    def is_cross_domain(self) -> bool:
        return self.domain_count >= 2


def _build_stage(
    *,
    index: int,
    domain: WorkflowDomain,
    steps: tuple[RunStepState, ...],
) -> WorkflowStageState:
    return WorkflowStageState(
        index=index,
        domain=domain,
        start_step=steps[0].index,
        end_step=steps[-1].index,
        actions=tuple(step.action for step in steps),
        successful_step_count=sum(step.success for step in steps),
        failed_step_count=sum(not step.success for step in steps),
        evidence_step_count=sum(bool(step.evidence) for step in steps),
        effect_dispatched_count=sum(
            step.effect_dispatched is True
            for step in steps
        ),
        postcondition_verified_count=sum(
            step.postcondition_verified is True
            for step in steps
        ),
    )


def summarize_composed_workflow(
    run_state: LyraRunState,
) -> ComposedWorkflowState | None:
    grouped: list[tuple[WorkflowDomain, list[RunStepState]]] = []

    for step in run_state.steps:
        domain = workflow_domain_for_action(step.action)
        if grouped and grouped[-1][0] is domain:
            grouped[-1][1].append(step)
        else:
            grouped.append((domain, [step]))

    stages = tuple(
        _build_stage(
            index=index,
            domain=domain,
            steps=tuple(steps),
        )
        for index, (domain, steps) in enumerate(grouped, start=1)
    )

    current_action = run_state.current_action
    current_domain = (
        workflow_domain_for_action(current_action)
        if current_action is not None
        else None
    )

    state = ComposedWorkflowState(
        run_id=run_state.run_id,
        goal=run_state.goal,
        status=run_state.status,
        stages=stages,
        current_action=current_action,
        current_domain=current_domain,
        file_workflow=summarize_file_workflow(run_state),
    )

    if not state.is_cross_domain:
        return None
    return state
