from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TaskTimeline
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("provider continuation not authorized")

    def reply(self, text, *, history=()):
        raise AssertionError("provider reply not authorized")


class DryPool:
    def __init__(self) -> None:
        self.workers: list[object] = []

    def start(self, worker) -> None:
        self.workers.append(worker)


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = ControlledProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def view(text: str, terminal: bool) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=text, terminal=terminal)


def test_m145_summary_empty_is_fixed_and_bounded() -> None:
    assert TaskTimeline().summary() == "Resumo: 0/12 eventos · sem registros"


def test_m145_summary_started_is_nonterminal() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: iniciada · 0/4 etapas", False))
    assert timeline.summary() == "Resumo: 1/12 eventos · em acompanhamento"


def test_m145_summary_direct_request_is_not_dispatched() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: solicitada · open_application", False))
    assert "ação solicitada, sem resultado" in timeline.summary()


def test_m145_summary_direct_verified_requires_terminal_view() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: pós-condição verificada · open_application", True))
    assert "pós-condição verificada" in timeline.summary()


def test_m145_summary_no_fake_verified_for_nonterminal_view() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: pós-condição verificada · open_application", False))
    assert "pós-condição verificada" not in timeline.summary()


def test_m145_summary_dispatched_does_not_claim_verification() -> None:
    timeline = TaskTimeline()
    timeline.record(
        view("Ação direta: efeito despachado, pós-condição não comprovada · open_application", True)
    )
    assert "despachado, não verificado" in timeline.summary()
    assert "pós-condição verificada" not in timeline.summary()


def test_m145_summary_received_does_not_claim_effect() -> None:
    timeline = TaskTimeline()
    timeline.record(
        view("Ação direta: resultado recebido, efeito não comprovado · open_application", True)
    )
    assert "resultado recebido, não comprovado" in timeline.summary()


def test_m145_summary_direct_failure_without_raw_result() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: falha reportada · open_application", True))
    assert "falha reportada" in timeline.summary()
    assert "open_application" not in timeline.summary()


def test_m145_summary_completed_not_verified() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: concluída · 2/4 etapas · sistema", True))
    assert "tarefa concluída, sem atestar efeitos" in timeline.summary()


def test_m145_summary_cancel_request_not_terminal() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    assert "cancelamento pendente" in timeline.summary()
    assert "cancelada" not in timeline.summary()


def test_m145_summary_confirmed_cancel_is_separate() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    timeline.record(view("Tarefa: cancelada · 0/4 etapas", True))
    assert timeline.summary() == "Resumo: 2/12 eventos · cancelada"


def test_m145_summary_failed_workflow() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falhou · 0/4 etapas", True))
    assert "falha sinalizada" in timeline.summary()


def test_m145_summary_processing_error_without_raw_error() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falha no processamento · efeito não comprovado", True))
    assert "falha de processamento" in timeline.summary()


def test_m145_summary_invalid_result_without_raw_reply() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: resultado inválido · efeito não comprovado", True))
    assert "resultado inválido" in timeline.summary()


def test_m145_summary_unclassified_terminal_fails_closed() -> None:
    timeline = TaskTimeline()
    timeline.record(view("PRIVATE_UNRECOGNIZED_STATUS", True))
    assert "estado não classificado" in timeline.summary()
    assert "PRIVATE" not in timeline.summary()


def test_m145_summary_rejects_fake_terminal_status() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelada · 0/4 etapas", False))
    assert "cancelada" not in timeline.summary()


def test_m145_summary_count_rolls_with_twelve_events() -> None:
    timeline = TaskTimeline()
    for index in range(23):
        timeline.record(view(f"Tarefa: etapa {index}", False))
    assert len(timeline.snapshot()) == 12
    assert timeline.summary() == "Resumo: 12/12 eventos · em acompanhamento"


def test_m145_summary_deduplicated_and_cleared() -> None:
    timeline = TaskTimeline()
    event = view("Tarefa: iniciada · 0/4 etapas", False)
    assert timeline.record(event)
    assert not timeline.record(event)
    assert timeline.summary().startswith("Resumo: 1/12")
    timeline.clear()
    assert timeline.summary() == "Resumo: 0/12 eventos · sem registros"


def test_m145_host_summary_label_is_read_only(host) -> None:
    window, provider, _, _ = host
    assert window.task_summary.objectName() == "lyra_task_summary"
    assert window.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
    assert provider.calls == 0


def test_m145_host_states_refresh_summary_without_dispatch(host) -> None:
    window, provider, _, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    assert window.task_summary.text() == "Resumo: 1/12 eventos · em acompanhamento"
    assert len(dry.workers) == 0
    assert provider.calls == 0


def test_m145_host_cancel_request_then_terminal_state(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE_TASK", ())
    assert len(dry.workers) == 1
    window._cancel_active_task()
    assert "cancelamento pendente" in window.task_summary.text()
    cancelled = LyraRunState.start("PRIVATE_GOAL", max_steps=4).cancel("PRIVATE_REASON")
    window._on_tool_state(cancelled)
    assert window.task_summary.text().endswith("cancelada")
    assert "PRIVATE" not in window.task_summary.text()
    assert provider.calls == 0


def test_m145_host_direct_evidence_status_distinct(host) -> None:
    window, provider, _, dry = host
    request = ActionRequest(action="open_application", arguments={"path": "PRIVATE_PATH"})
    window._start_action(request)
    assert "sem resultado" in window.task_summary.text()
    result = ActionResult(
        request_id=request.request_id, success=True,
        message="PRIVATE_RESULT", effect_dispatched=True,
        postcondition_verified=False,
    )
    window._on_action_result(result)
    assert "despachado, não verificado" in window.task_summary.text()
    assert "PRIVATE" not in window.task_summary.text()
    assert len(dry.workers) == 1 and provider.calls == 0


def test_m145_host_reset_and_separate_windows(host, monkeypatch) -> None:
    window, provider, memory, dry = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(),  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window._start_tool_task("PRIVATE_TASK", ())
        window._cancel_active_task()
        assert "cancelamento pendente" in window.task_summary.text()
        assert other.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
        window._set_busy(False)
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        window.session_reset.click()
        assert window.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
        assert window._memory is memory
        assert provider.calls == other_provider.calls == 0
        assert len(dry.workers) == 1
    finally:
        other.close()
