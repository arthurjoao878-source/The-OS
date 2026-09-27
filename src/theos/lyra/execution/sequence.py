from __future__ import annotations

from dataclasses import dataclass

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry

MAX_ACTION_SEQUENCE_STEPS = 4


@dataclass(frozen=True, slots=True)
class ActionSequenceResult:
    planned_steps: int
    results: tuple[ActionResult, ...]

    def __post_init__(self) -> None:
        if self.planned_steps < 1 or self.planned_steps > MAX_ACTION_SEQUENCE_STEPS:
            raise ValueError(
                f"planned_steps must be between 1 and {MAX_ACTION_SEQUENCE_STEPS}"
            )
        if len(self.results) > self.planned_steps:
            raise ValueError("results cannot exceed planned_steps")

    @property
    def completed_steps(self) -> int:
        return len(self.results)

    @property
    def success(self) -> bool:
        return (
            self.completed_steps == self.planned_steps
            and all(result.success for result in self.results)
        )


class SequentialActionExecutor:
    """Executes registered actions in order and stops immediately after a failure."""

    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        requests: tuple[ActionRequest, ...],
    ) -> ActionSequenceResult:
        if not requests:
            raise ValueError("action sequence must not be empty")
        if len(requests) > MAX_ACTION_SEQUENCE_STEPS:
            raise ValueError(
                f"action sequence supports at most {MAX_ACTION_SEQUENCE_STEPS} steps"
            )
        if not all(isinstance(request, ActionRequest) for request in requests):
            raise TypeError("sequence entries must be ActionRequest instances")

        results: list[ActionResult] = []
        for request in requests:
            result = self._registry.execute(request)
            results.append(result)
            if not result.success:
                break

        return ActionSequenceResult(
            planned_steps=len(requests),
            results=tuple(results),
        )
