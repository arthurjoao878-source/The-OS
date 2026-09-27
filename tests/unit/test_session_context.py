from __future__ import annotations

from theos.lyra.context import ConversationRole, SessionContext


def test_session_context_is_bounded_and_keeps_visible_order() -> None:
    context = SessionContext(max_turns=3)

    context.add_user("primeiro")
    context.add_assistant("segundo")
    context.add_user("terceiro")
    context.add_assistant("quarto")

    snapshot = context.snapshot()

    assert [(turn.role, turn.text) for turn in snapshot] == [
        (ConversationRole.ASSISTANT, "segundo"),
        (ConversationRole.USER, "terceiro"),
        (ConversationRole.ASSISTANT, "quarto"),
    ]
