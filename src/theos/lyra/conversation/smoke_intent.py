from __future__ import annotations

import re

from theos.core.actions.contracts import ActionRequest

_OPEN_RE = re.compile(
    r"^\s*(?:lyra[, ]+)?(?:abre|abrir|open)\s+(?:o\s+|a\s+)?(?P<app>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def resolve_smoke_intent(text: str) -> ActionRequest | None:
    match = _OPEN_RE.match(text)
    if not match:
        return None

    app = match.group("app").strip()
    return ActionRequest(
        action="open_application",
        arguments={"application": app},
    )