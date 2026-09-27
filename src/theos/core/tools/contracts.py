from __future__ import annotations

from dataclasses import dataclass

MAX_TOOL_PLAN_STEPS = 4


class ToolValidationError(ValueError):
    """A proposed tool call did not satisfy the local tool contract."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be blank")
        if not self.description.strip():
            raise ValueError("tool description must not be blank")
        if not isinstance(self.parameters, dict):
            raise TypeError("tool parameters must be a dict")


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, object]
    call_id: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool call name must not be blank")
        if not isinstance(self.arguments, dict):
            raise TypeError("tool call arguments must be a dict")
        if self.call_id is not None and not self.call_id.strip():
            raise ValueError("call_id must be a non-blank string or None")


@dataclass(frozen=True, slots=True)
class ToolPlan:
    calls: tuple[ToolCall, ...]

    def __post_init__(self) -> None:
        if len(self.calls) < 2:
            raise ValueError("tool plan requires at least two calls")
        if len(self.calls) > MAX_TOOL_PLAN_STEPS:
            raise ValueError(f"tool plan supports at most {MAX_TOOL_PLAN_STEPS} calls")
        if not all(isinstance(call, ToolCall) for call in self.calls):
            raise TypeError("tool plan calls must be ToolCall instances")
