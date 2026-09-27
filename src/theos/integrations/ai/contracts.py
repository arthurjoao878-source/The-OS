from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from theos.core.tools import ToolCall, ToolDefinition
from theos.lyra.context import ConversationTurn


class AIProviderError(RuntimeError):
    """Safe provider failure that can be shown to the LYRA shell."""


@dataclass(frozen=True, slots=True)
class AIReply:
    text: str
    provider_id: str
    model: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("AI reply text must not be blank")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("provider_id must not be blank")
        if self.model is not None and (not isinstance(self.model, str) or not self.model.strip()):
            raise ValueError("model must be a non-blank string or None")


@dataclass(frozen=True, slots=True)
class AIContinuation:
    provider_id: str
    state: object

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be blank")


@dataclass(frozen=True, slots=True)
class AIToolTurn:
    calls: tuple[ToolCall, ...]
    continuation: AIContinuation
    provider_id: str
    model: str | None = None

    def __post_init__(self) -> None:
        if not self.calls:
            raise ValueError("tool turn must contain at least one call")
        if not all(isinstance(call, ToolCall) for call in self.calls):
            raise TypeError("tool turn calls must be ToolCall instances")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be blank")
        if self.model is not None and not self.model.strip():
            raise ValueError("model must be a non-blank string or None")


@dataclass(frozen=True, slots=True)
class AIToolResult:
    call_id: str
    output: str

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("call_id must not be blank")
        if not self.output.strip():
            raise ValueError("tool output must not be blank")


AIResponse = AIReply | AIToolTurn


@runtime_checkable
class AIProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def respond(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
        tools: tuple[ToolDefinition, ...] = (),
    ) -> AIResponse: ...

    def continue_after_tools(
        self,
        turn: AIToolTurn,
        results: tuple[AIToolResult, ...],
    ) -> AIResponse: ...

    def reply(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
    ) -> AIReply: ...


class UnavailableAIProvider:
    provider_id = "unavailable"

    def __init__(self, reason: str) -> None:
        normalized = reason.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        self._reason = normalized

    def respond(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
        tools: tuple[ToolDefinition, ...] = (),
    ) -> AIResponse:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must not be blank")
        _ = history, tools
        return AIReply(
            text=self._reason,
            provider_id=self.provider_id,
            model=None,
        )

    def continue_after_tools(
        self,
        turn: AIToolTurn,
        results: tuple[AIToolResult, ...],
    ) -> AIResponse:
        _ = turn, results
        raise AIProviderError("O provedor de IA não está disponível para continuar ferramentas.")

    def reply(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
    ) -> AIReply:
        response = self.respond(text, history=history)
        if not isinstance(response, AIReply):
            raise AIProviderError("O provedor indisponível retornou uma ferramenta.")
        return response
