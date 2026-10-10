from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from theos.core.actions.contracts import ActionResult
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

TASK_TIMELINE_LIMIT = 12
TASK_TIMELINE_MAX_ENTRY_CHARS = 180
TASK_TIMELINE_EMPTY = "Sem etapas de tarefa nesta sessão."
TASK_TIMELINE_INTERRUPTIONS_EMPTY = "Sem interrupções nos eventos recentes."


def _is_interruption(text: str, terminal: bool | None) -> bool:
    """Accept only fixed, presentation-only interruption labels."""
    if terminal is False:
        return text == "Tarefa: cancelamento solicitado · aguardando confirmação"
    if terminal is not True:
        return False
    if text in (
        "Tarefa: falha no processamento · efeito não comprovado",
        "Tarefa: resultado inválido · efeito não comprovado",
    ):
        return True
    if re.fullmatch(r"Ação direta: falha reportada · [a-z][a-z0-9_]{0,47}", text):
        return True
    step = r"[0-9]{1,4}/[1-9][0-9]{0,3} etapas"
    if re.fullmatch(rf"Tarefa: cancelada · {step}", text):
        return True
    domain = r"(?:aplicativo|desenvolvimento|arquivo|outro|processo|sistema|janela)"
    return re.fullmatch(rf"Tarefa: falhou · {step}(?: · {domain})?", text) is not None


@dataclass(slots=True)
class TaskTimeline:
    """Recent presentation-only task states, never arguments or raw evidence."""

    _entries: list[str] = field(default_factory=list)
    _latest_terminal: bool | None = None
    _interruption_flags: list[bool] = field(default_factory=list)

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
        terminal = view.terminal if type(view.terminal) is bool else None
        if self._entries and self._entries[-1] == text:
            # A later terminal signal for an identical label is a real state
            # transition; update the current event instead of losing it.
            # Never downgrade an already terminal event or inflate the count.
            if self._latest_terminal is False and terminal is True:
                self._latest_terminal = True
                self._interruption_flags[-1] = _is_interruption(text, True)
                return True
            return False
        self._entries.append(text)
        self._latest_terminal = terminal
        self._interruption_flags.append(_is_interruption(text, terminal))
        if len(self._entries) > TASK_TIMELINE_LIMIT:
            del self._entries[:-TASK_TIMELINE_LIMIT]
            del self._interruption_flags[:-TASK_TIMELINE_LIMIT]
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._latest_terminal = None
        self._interruption_flags.clear()

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def display(self) -> str:
        if not self._entries:
            return TASK_TIMELINE_EMPTY
        return "\n".join(
            f"{index}. {entry}" for index, entry in enumerate(self._entries, 1)
        )

    def display_interruptions(self) -> str:
        """A read-only, bounded filtered view; never mutates the event history."""
        matches = [
            f"{index}. {text}"
            for index, (text, flagged) in enumerate(
                zip(self._entries, self._interruption_flags, strict=True), 1
            )
            if flagged
        ]
        return "\n".join(matches) if matches else TASK_TIMELINE_INTERRUPTIONS_EMPTY

    def display_interruption_category(self, category: str) -> str:
        """Filter only previously recognized interruptions by a finite safe category."""
        if type(category) is not str or category not in (
            "all", "pending", "cancelled", "failed"
        ):
            return TASK_TIMELINE_INTERRUPTIONS_EMPTY
        if category == "all":
            return self.display_interruptions()
        matches = [
            f"{index}. {text}"
            for index, (text, flagged) in enumerate(
                zip(self._entries, self._interruption_flags, strict=True), 1
            )
            if flagged
            and (
                "pending"
                if text == "Tarefa: cancelamento solicitado · aguardando confirmação"
                else "cancelled"
                if text.startswith("Tarefa: cancelada · ")
                else "failed"
            ) == category
        ]
        return "\n".join(matches) if matches else TASK_TIMELINE_INTERRUPTIONS_EMPTY

    def visible_view_scope_label(self, *, interruptions_only: bool, category: str) -> str:
        """Fixed read-only name for the selected, bounded presentation view."""
        if type(interruptions_only) is not bool:
            return "Visão: indisponível"
        if not interruptions_only:
            return "Visão: histórico completo"
        labels = {
            "all": "todas",
            "pending": "pendentes",
            "cancelled": "canceladas",
            "failed": "falhas",
        }
        if type(category) is not str or category not in labels:
            return "Visão: indisponível"
        return "Visão: interrupções · " + labels[category]

    def visible_entry_count_label(self, *, interruptions_only: bool, category: str) -> str:
        """Count only entries in the current safe, bounded presentation view."""
        if type(interruptions_only) is not bool:
            count = 0
        elif not interruptions_only:
            count = len(self._entries)
        else:
            display = self.display_interruption_category(category)
            count = (
                0
                if display == TASK_TIMELINE_INTERRUPTIONS_EMPTY
                else len(display.splitlines())
            )
        return f"Na lista: {count}/{TASK_TIMELINE_LIMIT} eventos recentes"

    def interruption_count_label(self) -> str:
        """Read-only count of already-classified presentations in the last 12."""
        return (
            f"Interrupções: {sum(self._interruption_flags)}/"
            f"{TASK_TIMELINE_LIMIT} eventos recentes"
        )

    def interruption_breakdown_label(self) -> str:
        """Counts only previously validated presentation flags in the last 12."""
        pending = cancelled = failed = 0
        for text, flagged in zip(
            self._entries, self._interruption_flags, strict=True
        ):
            if not flagged:
                continue
            if text == "Tarefa: cancelamento solicitado · aguardando confirmação":
                pending += 1
            elif text.startswith("Tarefa: cancelada · "):
                cancelled += 1
            else:
                failed += 1
        return (
            f"Tipos: pendentes {pending} · canceladas {cancelled} · falhas {failed}"
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
