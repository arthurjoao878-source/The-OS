from __future__ import annotations

from dataclasses import dataclass

from theos.lyra.execution.composed_workflow import WorkflowDomain
from theos.lyra.execution.run_state import LyraRunState
from theos.lyra.execution.workflow_progress import (
    WorkflowProgressKind,
    WorkflowProgressState,
    summarize_workflow_progress,
)

HOST_WORKFLOW_PROGRESS_VERSION = 1

_DOMAIN_LABELS = {
    WorkflowDomain.APPLICATION: "aplicativo",
    WorkflowDomain.DEVELOPMENT: "desenvolvimento",
    WorkflowDomain.FILE: "arquivo",
    WorkflowDomain.OTHER: "outro",
    WorkflowDomain.PROCESS: "processo",
    WorkflowDomain.SYSTEM: "sistema",
    WorkflowDomain.WINDOW: "janela",
}


@dataclass(frozen=True, slots=True)
class HostWorkflowProgressView:
    text: str
    terminal: bool
    version: int = HOST_WORKFLOW_PROGRESS_VERSION

    def __post_init__(self) -> None:
        normalized = self.text.strip()
        if not normalized:
            raise ValueError("host workflow progress text must not be blank")
        object.__setattr__(self, "text", normalized)
        if self.version != HOST_WORKFLOW_PROGRESS_VERSION:
            raise ValueError("unsupported host workflow progress version")


def _domain_label(domain: WorkflowDomain | None) -> str | None:
    if domain is None:
        return None
    return _DOMAIN_LABELS[domain]


def present_workflow_progress(
    progress: WorkflowProgressState,
) -> HostWorkflowProgressView:
    steps = f"{progress.completed_steps}/{progress.max_steps} etapas"

    if progress.kind is WorkflowProgressKind.STARTED:
        text = f"Tarefa: iniciada · {steps}"
        terminal = False
    elif progress.kind is WorkflowProgressKind.ACTION_RUNNING:
        domain = _domain_label(progress.current_domain)
        text = (
            f"Tarefa: executando {progress.current_action} · "
            f"{domain} · {steps}"
        )
        terminal = False
    elif progress.kind is WorkflowProgressKind.AWAITING_CONFIRMATION:
        domain = _domain_label(progress.current_domain)
        text = (
            f"Tarefa: aguardando confirmação · {progress.current_action} · "
            f"{domain} · {steps}"
        )
        terminal = False
    elif progress.kind is WorkflowProgressKind.STEP_COMPLETED:
        domain = _domain_label(progress.last_completed_domain)
        text = (
            f"Tarefa: etapa {progress.completed_steps}/{progress.max_steps} concluída · "
            f"{progress.last_completed_action} · {domain}"
        )
        terminal = False
    elif progress.kind is WorkflowProgressKind.COMPLETED:
        domain = _domain_label(progress.last_completed_domain)
        suffix = f" · {domain}" if domain is not None else ""
        text = f"Tarefa: concluída · {steps}{suffix}"
        terminal = True
    elif progress.kind is WorkflowProgressKind.FAILED:
        domain = _domain_label(progress.last_completed_domain)
        suffix = f" · {domain}" if domain is not None else ""
        text = f"Tarefa: falhou · {steps}{suffix}"
        terminal = True
    elif progress.kind is WorkflowProgressKind.CANCELLED:
        text = f"Tarefa: cancelada · {steps}"
        terminal = True
    else:
        raise ValueError(f"unsupported workflow progress kind: {progress.kind!r}")

    return HostWorkflowProgressView(
        text=text,
        terminal=terminal,
    )


def present_run_state(
    run_state: LyraRunState,
) -> HostWorkflowProgressView:
    return present_workflow_progress(
        summarize_workflow_progress(run_state)
    )
