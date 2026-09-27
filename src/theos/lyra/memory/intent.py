from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class MemoryIntentKind(StrEnum):
    REMEMBER = "remember"
    SEARCH = "search"


@dataclass(frozen=True, slots=True)
class MemoryIntent:
    kind: MemoryIntentKind
    text: str


_REMEMBER_RE = re.compile(
    r"^\s*(?:lyra[, ]+)?(?:lembre|memorize|guarde)\s+(?:que\s+)?(?P<text>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_SEARCH_RE = re.compile(
    r"^\s*(?:lyra[, ]+)?(?:"
    r"o\s+que\s+(?:você|voce)\s+(?:lembra|sabe)\s+(?:sobre|de)"
    r"|procure\s+na\s+mem[oó]ria\s+(?:por\s+)?"
    r"|busque\s+na\s+mem[oó]ria\s+(?:por\s+)?"
    r"|consulte\s+(?:a\s+)?mem[oó]ria\s+(?:sobre\s+)?"
    r")\s+(?P<text>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def resolve_memory_intent(text: str) -> MemoryIntent | None:
    remember = _REMEMBER_RE.match(text)
    if remember:
        value = remember.group("text").strip()
        if value:
            return MemoryIntent(MemoryIntentKind.REMEMBER, value)

    search = _SEARCH_RE.match(text)
    if search:
        value = search.group("text").strip()
        if value:
            return MemoryIntent(MemoryIntentKind.SEARCH, value)

    return None
