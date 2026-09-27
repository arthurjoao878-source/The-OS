from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from theos.core.actions.contracts import ActionRequest
from theos.lyra.conversation.smoke_intent import resolve_smoke_intent
from theos.lyra.memory.intent import MemoryIntent, resolve_memory_intent


class PlanKind(StrEnum):
    MEMORY = "memory"
    ACTION = "action"
    CONVERSATION = "conversation"


@dataclass(frozen=True, slots=True)
class LyraPlan:
    kind: PlanKind
    original_text: str
    memory_intent: MemoryIntent | None = None
    action_request: ActionRequest | None = None

    def __post_init__(self) -> None:
        normalized = self.original_text.strip()
        if not normalized:
            raise ValueError("original_text must not be blank")
        object.__setattr__(self, "original_text", normalized)

        if self.kind is PlanKind.MEMORY:
            if self.memory_intent is None or self.action_request is not None:
                raise ValueError("memory plan requires only memory_intent")
        elif self.kind is PlanKind.ACTION:
            if self.action_request is None or self.memory_intent is not None:
                raise ValueError("action plan requires only action_request")
        elif self.kind is PlanKind.CONVERSATION:
            if self.memory_intent is not None or self.action_request is not None:
                raise ValueError("conversation plan cannot contain local execution payloads")
        else:
            raise ValueError(f"unsupported plan kind: {self.kind!r}")


class LyraPlanner:
    """Routes a user turn while preserving local memory/action priority over AI."""

    def plan(self, text: str) -> LyraPlan:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be blank")

        memory_intent = resolve_memory_intent(normalized)
        if memory_intent is not None:
            return LyraPlan(
                kind=PlanKind.MEMORY,
                original_text=normalized,
                memory_intent=memory_intent,
            )

        action_request = resolve_smoke_intent(normalized)
        if action_request is not None:
            return LyraPlan(
                kind=PlanKind.ACTION,
                original_text=normalized,
                action_request=action_request,
            )

        return LyraPlan(
            kind=PlanKind.CONVERSATION,
            original_text=normalized,
        )
