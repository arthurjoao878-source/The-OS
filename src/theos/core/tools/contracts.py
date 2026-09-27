from __future__ import annotations

from dataclasses import dataclass


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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool call name must not be blank")
        if not isinstance(self.arguments, dict):
            raise TypeError("tool call arguments must be a dict")
