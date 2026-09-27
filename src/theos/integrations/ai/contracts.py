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


AIResponse = AIReply | ToolCall


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
