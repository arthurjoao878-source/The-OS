from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    role: ConversationRole
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ConversationRole):
            raise TypeError("role must be ConversationRole")
        normalized = self.text.strip()
        if not normalized:
            raise ValueError("conversation turn text must not be blank")
        object.__setattr__(self, "text", normalized)


class SessionContext:
    """Bounded, in-memory context for visible LYRA conversation turns."""

    def __init__(self, *, max_turns: int = 12) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    @property
    def max_turns(self) -> int:
        maxlen = self._turns.maxlen
        if maxlen is None:
            raise RuntimeError("session context must be bounded")
        return maxlen

    def add_user(self, text: str) -> ConversationTurn:
        return self._append(ConversationRole.USER, text)

    def add_assistant(self, text: str) -> ConversationTurn:
        return self._append(ConversationRole.ASSISTANT, text)

    def snapshot(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    def clear(self) -> None:
        self._turns.clear()

    def _append(self, role: ConversationRole, text: str) -> ConversationTurn:
        turn = ConversationTurn(role=role, text=text)
        self._turns.append(turn)
        return turn
