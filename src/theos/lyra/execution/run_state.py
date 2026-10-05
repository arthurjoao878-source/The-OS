from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from theos.core.actions.contracts import ActionRequest, ActionResult

LYRA_RUN_STATE_VERSION = 1


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class RunStepState:
    index: int
    action: str
    request_id: UUID
    success: bool
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    effect_dispatched: bool | None = None
    postcondition_verified: bool | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("run step index must be positive")
        normalized_action = self.action.strip()
        if not normalized_action:
            raise ValueError("run step action must not be blank")
        object.__setattr__(self, "action", normalized_action)
        object.__setattr__(self, "evidence", deepcopy(self.evidence))

    @classmethod
    def from_action_result(
        cls,
        *,
        index: int,
        request: ActionRequest,
        result: ActionResult,
    ) -> RunStepState:
        if result.request_id != request.request_id:
            raise ValueError("action result request_id does not match request")

        return cls(
            index=index,
            action=request.action,
            request_id=request.request_id,
            success=result.success,
            message=result.message,
            evidence=result.evidence,
            error_code=result.error_code,
            effect_dispatched=result.effect_dispatched,
            postcondition_verified=result.postcondition_verified,
        )


@dataclass(frozen=True, slots=True)
class LyraRunState:
    run_id: UUID
    goal: str
    status: RunStatus
    max_steps: int
    steps: tuple[RunStepState, ...] = ()
    current_action: str | None = None
    current_request_id: UUID | None = None
    final_reply: str | None = None
    error: str | None = None
    version: int = LYRA_RUN_STATE_VERSION

    def __post_init__(self) -> None:
        normalized_goal = self.goal.strip()
        if not normalized_goal:
            raise ValueError("run goal must not be blank")
        object.__setattr__(self, "goal", normalized_goal)

        if self.version != LYRA_RUN_STATE_VERSION:
            raise ValueError("unsupported LYRA run state version")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if len(self.steps) > self.max_steps:
            raise ValueError("run steps exceed max_steps")

        for expected_index, step in enumerate(self.steps, start=1):
            if step.index != expected_index:
                raise ValueError("run step indexes must be contiguous")

        has_current_action = self.current_action is not None
        has_current_request = self.current_request_id is not None
        if has_current_action != has_current_request:
            raise ValueError(
                "current_action and current_request_id must be set together"
            )
        if self.current_action is not None and not self.current_action.strip():
            raise ValueError("current_action must not be blank")

        if self.status is RunStatus.AWAITING_CONFIRMATION:
            if not has_current_action:
                raise ValueError(
                    "awaiting confirmation requires a current action"
                )
            if self.final_reply is not None or self.error is not None:
                raise ValueError(
                    "awaiting confirmation cannot be final or errored"
                )
            return

        if self.status is RunStatus.COMPLETED:
            if has_current_action:
                raise ValueError("completed run cannot have a current action")
            if self.final_reply is None or not self.final_reply.strip():
                raise ValueError("completed run requires final_reply")
            if self.error is not None:
                raise ValueError("completed run cannot contain error")
            return

        if self.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
            if has_current_action:
                raise ValueError("terminal run cannot have a current action")
            if self.error is None or not self.error.strip():
                raise ValueError("failed or cancelled run requires error")
            if self.final_reply is not None:
                raise ValueError(
                    "failed or cancelled run cannot contain final_reply"
                )
            return

        if self.status is RunStatus.RUNNING:
            if self.final_reply is not None or self.error is not None:
                raise ValueError("running run cannot be final or errored")
            return

        raise ValueError(f"unsupported run status: {self.status!r}")

    @classmethod
    def start(cls, goal: str, *, max_steps: int) -> LyraRunState:
        return cls(
            run_id=uuid4(),
            goal=goal,
            status=RunStatus.RUNNING,
            max_steps=max_steps,
        )

    @property
    def completed_steps(self) -> int:
        return len(self.steps)

    @property
    def remaining_step_budget(self) -> int:
        return self.max_steps - self.completed_steps

    def begin_action(self, request: ActionRequest) -> LyraRunState:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running run can begin an action")
        if self.current_action is not None:
            raise ValueError("run already has a current action")
        if self.remaining_step_budget < 1:
            raise ValueError("run step budget exhausted")

        return replace(
            self,
            current_action=request.action,
            current_request_id=request.request_id,
        )

    def wait_for_confirmation(
        self,
        request: ActionRequest,
    ) -> LyraRunState:
        running = self.begin_action(request)
        return replace(
            running,
            status=RunStatus.AWAITING_CONFIRMATION,
        )

    def resume_after_confirmation(self) -> LyraRunState:
        if self.status is not RunStatus.AWAITING_CONFIRMATION:
            raise ValueError("run is not awaiting confirmation")

        return replace(
            self,
            status=RunStatus.RUNNING,
        )

    def record_action(
        self,
        request: ActionRequest,
        result: ActionResult,
    ) -> LyraRunState:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running run can record an action")
        if self.current_request_id != request.request_id:
            raise ValueError("current request does not match action result")
        if self.current_action != request.action:
            raise ValueError("current action does not match request")
        if self.remaining_step_budget < 1:
            raise ValueError("run step budget exhausted")

        step = RunStepState.from_action_result(
            index=self.completed_steps + 1,
            request=request,
            result=result,
        )
        return replace(
            self,
            steps=(*self.steps, step),
            current_action=None,
            current_request_id=None,
        )

    def complete(self, final_reply: str) -> LyraRunState:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running run can complete")
        if self.current_action is not None:
            raise ValueError("cannot complete while an action is current")
        normalized = final_reply.strip()
        if not normalized:
            raise ValueError("final_reply must not be blank")

        return replace(
            self,
            status=RunStatus.COMPLETED,
            final_reply=normalized,
        )

    def fail(self, error: str) -> LyraRunState:
        if self.status not in {
            RunStatus.RUNNING,
            RunStatus.AWAITING_CONFIRMATION,
        }:
            raise ValueError("only an active run can fail")
        normalized = error.strip()
        if not normalized:
            raise ValueError("error must not be blank")

        return replace(
            self,
            status=RunStatus.FAILED,
            current_action=None,
            current_request_id=None,
            error=normalized,
        )

    def cancel(self, error: str) -> LyraRunState:
        if self.status not in {
            RunStatus.RUNNING,
            RunStatus.AWAITING_CONFIRMATION,
        }:
            raise ValueError("only an active run can be cancelled")
        normalized = error.strip()
        if not normalized:
            raise ValueError("error must not be blank")

        return replace(
            self,
            status=RunStatus.CANCELLED,
            current_action=None,
            current_request_id=None,
            error=normalized,
        )
