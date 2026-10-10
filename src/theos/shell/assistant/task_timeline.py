from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from theos.core.actions.contracts import ActionResult
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

TASK_TIMELINE_LIMIT = 12
TASK_TIMELINE_MAX_ENTRY_CHARS = 180
TASK_TIMELINE_EMPTY = "Sem etapas de tarefa nesta sessão."


@dataclass(slots=True)
class TaskTimeline:
    """Recent presentation-only task states, never arguments or raw evidence."""

    _entries: list[str] = field(default_factory=list)
    _latest_terminal: bool | None = None

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
        self._latest_terminal = view.terminal if type(view.terminal) is bool else None
        if len(self._entries) > TASK_TIMELINE_LIMIT:
            del self._entries[:-TASK_TIMELINE_LIMIT]
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._latest_terminal = None

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def display(self) -> str:
        if not self._entries:
            return TASK_TIMELINE_EMPTY
        return "\n".join(
            f"{index}. {entry}" for index, entry in enumerate(self._entries, 1)
        )

    def summary(self) -> str:
        """Fixed labels about bounded visible events; never proof of unseen effects."""
        if not self._entries:
            return "Resumo: 0/12 eventos · sem registros"
        last = self._entries[-1]
        status = "estado não classificado"
        if self._latest_terminal is True:
            if last.startswith("Ação direta: pós-condição verificada · "):
                status = "pós-condição verificada"
            elif last.startswith("Ação direta: efeito despachado, pós-condição não comprovada · "):
                status = "despachado, não verificado"
            elif last.startswith("Ação direta: resultado recebido, efeito não comprovado · "):
                status = "resultado recebido, não comprovado"
            elif last.startswith("Ação direta: falha reportada · "):
                status = "falha reportada"
            elif last.startswith("Tarefa: concluída · "):
                status = "tarefa concluída, sem atestar efeitos"
            elif last.startswith("Tarefa: cancelada · "):
                status = "cancelada"
            elif last.startswith("Tarefa: falhou · "):
                status = "falha sinalizada"
            elif last == "Tarefa: falha no processamento · efeito não comprovado":
                status = "falha de processamento"
            elif last == "Tarefa: resultado inválido · efeito não comprovado":
                status = "resultado inválido"
        elif self._latest_terminal is False:
            if last == "Tarefa: cancelamento solicitado · aguardando confirmação":
                status = "cancelamento pendente"
            elif last.startswith("Tarefa: aguardando confirmação · "):
                status = "aguardando confirmação"
            elif last.startswith("Ação direta: solicitada · "):
                status = "ação solicitada, sem resultado"
            else:
                status = "em acompanhamento"
        return f"Resumo: {len(self._entries)}/{TASK_TIMELINE_LIMIT} eventos · {status}"


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


class TaskInterruptionKind(StrEnum):
    """Presentation-only host signals; never evidence of a dispatched effect."""

    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    INVALID_RESULT = "INVALID_RESULT"


def present_task_interruption(
    kind: TaskInterruptionKind,
) -> HostWorkflowProgressView | None:
    """Bounded fixed phrases, never raw provider errors or task arguments."""
    if not isinstance(kind, TaskInterruptionKind):
        return None
    if kind is TaskInterruptionKind.CANCEL_REQUESTED:
        return HostWorkflowProgressView(
            text="Tarefa: cancelamento solicitado · aguardando confirmação",
            terminal=False,
        )
    if kind is TaskInterruptionKind.PROCESSING_FAILED:
        return HostWorkflowProgressView(
            text="Tarefa: falha no processamento · efeito não comprovado",
            terminal=True,
        )
    if kind is TaskInterruptionKind.INVALID_RESULT:
        return HostWorkflowProgressView(
            text="Tarefa: resultado inválido · efeito não comprovado",
            terminal=True,
        )
    return None
