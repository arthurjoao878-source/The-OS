from __future__ import annotations

import re
from dataclasses import dataclass, field

from theos.core.actions.contracts import ActionResult
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

TASK_TIMELINE_LIMIT = 12
TASK_TIMELINE_MAX_ENTRY_CHARS = 180
TASK_TIMELINE_EMPTY = "Sem etapas de tarefa nesta sessão."


@dataclass(slots=True)
class TaskTimeline:
    """Recent presentation-only task states, never arguments or raw evidence."""

    _entries: list[str] = field(default_factory=list)

    def record(self, view: HostWorkflowProgressView) -> bool:
        if not isinstance(view, HostWorkflowProgressView):
            return False
        text = view.text
        if (
            not text
            or len(text) > TASK_TIMELINE_MAX_ENTRY_CHARS
            or any(ord(char) < 32 or ord(char) == 127 for char in text)
        ):
            return False
        if self._entries and self._entries[-1] == text:
            return False
        self._entries.append(text)
        if len(self._entries) > TASK_TIMELINE_LIMIT:
            del self._entries[:-TASK_TIMELINE_LIMIT]
        return True

    def clear(self) -> None:
        self._entries.clear()

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def display(self) -> str:
        if not self._entries:
            return TASK_TIMELINE_EMPTY
        return "\n".join(
            f"{index}. {entry}" for index, entry in enumerate(self._entries, 1)
        )


def present_direct_action_progress(
    action: str,
    *,
    result: ActionResult | None = None,
) -> HostWorkflowProgressView | None:
    """Present fixed, bounded action IDs; never render arguments or evidence."""
    if not isinstance(action, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,47}", action) is None:
        return None
    if result is None:
        return HostWorkflowProgressView(
            text=f"Ação direta: solicitada · {action}", terminal=False
        )
    if not isinstance(result, ActionResult):
        return None
    if not result.success:
        status = "falha reportada"
    elif result.postcondition_verified is True:
        status = "pós-condição verificada"
    elif result.effect_dispatched is True:
        status = "efeito despachado, pós-condição não comprovada"
    else:
        status = "resultado recebido, efeito não comprovado"
    return HostWorkflowProgressView(
        text=f"Ação direta: {status} · {action}", terminal=True
    )
