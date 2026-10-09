from __future__ import annotations

from theos.lyra.context import ConversationRole, SessionContext

MAX_DRAFT_RECALL_ITEMS = 8
MAX_DRAFT_RECALL_CHARS = 1024


def recallable_user_drafts(session: SessionContext) -> tuple[str, ...]:
    """Only complete, bounded user submissions from the active local session."""
    selected = [
        turn.text
        for turn in session.snapshot()
        if turn.role is ConversationRole.USER
        and len(turn.text) <= MAX_DRAFT_RECALL_CHARS
        and "\n" not in turn.text
        and "\r" not in turn.text
    ]
    return tuple(selected[-MAX_DRAFT_RECALL_ITEMS:])
