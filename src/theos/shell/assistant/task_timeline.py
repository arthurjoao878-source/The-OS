from __future__ import annotations

from dataclasses import dataclass, field

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
