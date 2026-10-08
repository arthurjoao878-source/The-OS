from __future__ import annotations

from theos.lyra.context.session import (
    MAX_PROVIDER_HISTORY_TOTAL_CHARS,
    MAX_PROVIDER_HISTORY_TURNS,
    SessionContext,
)
from theos.lyra.perception import PerceptionContext


def present_context_status(session: SessionContext, perception: PerceptionContext) -> str:
    """Display bounded counts only, never conversation or raw action evidence."""
    if not isinstance(session, SessionContext):
        raise TypeError("session must be SessionContext")
    if not isinstance(perception, PerceptionContext):
        raise TypeError("perception must be PerceptionContext")
    history = session.provider_snapshot()
    observed = perception.snapshot()
    characters = sum(len(turn.text) for turn in history)
    return (
        "Contexto (próximo pedido): "
        f"histórico {len(history)}/{MAX_PROVIDER_HISTORY_TURNS} turnos · "
        f"{characters}/{MAX_PROVIDER_HISTORY_TOTAL_CHARS} caracteres · "
        f"percepção {len(observed)}/{perception.max_observations}"
    )
