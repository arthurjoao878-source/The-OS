from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import (
    TASK_TIMELINE_INTERRUPTIONS_EMPTY,
    TASK_TIMELINE_LIMIT,
    TaskTimeline,
)
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="fake", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("no continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("no reply")


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


def view(label: str, terminal: bool) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=label, terminal=terminal)


def test_m146_empty_view_fixed() -> None:
    timeline = TaskTimeline()
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_non_issue_events_are_not_included() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: iniciada · 0/4 etapas", False))
    timeline.record(view("Tarefa: concluída · 0/4 etapas", True))
    timeline.record(view("Ação direta: resultado recebido, efeito não comprovado · system_status", True))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert len(timeline.snapshot()) == 3


def test_m146_cancel_requested_is_pending_not_confirmed() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    assert "cancelamento solicitado" in timeline.display_interruptions()
    assert "cancelada" not in timeline.display_interruptions()


def test_m146_cancelled_requires_terminal_view() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelada · 1/4 etapas", False))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    timeline.record(view("Tarefa: cancelada · 1/4 etapas", True))
    assert "cancelada" in timeline.display_interruptions()


def test_m146_failed_workflow_with_known_domain() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falhou · 2/4 etapas · arquivo", True))
    assert "Tarefa: falhou" in timeline.display_interruptions()


def test_m146_failed_workflow_unknown_domain_rejected() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falhou · 2/4 etapas · PRIVATE_DOMAIN", True))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_processing_failure_and_invalid_result_exact_only() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falha no processamento · efeito não comprovado", True))
    timeline.record(view("Tarefa: resultado inválido · efeito não comprovado", True))
    assert timeline.display_interruptions().count("efeito não comprovado") == 2


def test_m146_processing_failure_not_term_when_nonterminal() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falha no processamento · efeito não comprovado", False))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_direct_failure_safe_action_identifier_only() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: falha reportada · open_application", True))
    assert "open_application" in timeline.display_interruptions()
    timeline.record(view("Ação direta: falha reportada · PRIVATE/PATH", True))
    assert "PRIVATE" not in timeline.display_interruptions()


def test_m146_received_or_dispatched_not_a_failure() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Ação direta: efeito despachado, pós-condição não comprovada · open_application", True))
    timeline.record(view("Ação direta: resultado recebido, efeito não comprovado · open_application", True))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_unknown_fake_status_fails_closed() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelada · PRIVATE", True))
    timeline.record(view("Tarefa: falhou · 99/100000 etapas", True))
    timeline.record(view("PRIVADO", True))
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_preserves_original_event_numbers() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: iniciada · 0/4 etapas", False))
    timeline.record(view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    timeline.record(view("Tarefa: cancelada · 0/4 etapas", True))
    assert timeline.display_interruptions().startswith("2. Tarefa:")
    assert "\n3. Tarefa: cancelada" in timeline.display_interruptions()
    assert timeline.display().startswith("1. Tarefa: iniciada")


def test_m146_rolling_twelve_bounds_filtered_events() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: falha no processamento · efeito não comprovado", True))
    for number in range(20):
        timeline.record(view(f"Tarefa: etapa {number}", False))
    assert len(timeline.snapshot()) == TASK_TIMELINE_LIMIT
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_clear_removes_all_filter_state() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: cancelada · 0/4 etapas", True))
    timeline.clear()
    assert timeline.snapshot() == ()
    assert timeline.display_interruptions() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m146_adjacent_duplicate_unchanged() -> None:
    timeline = TaskTimeline()
    issue = view("Tarefa: falha no processamento · efeito não comprovado", True)
    assert timeline.record(issue)
    assert not timeline.record(issue)
    assert len(timeline.snapshot()) == 1
    assert timeline.display_interruptions().count("falha no processamento") == 1


def test_m146_filter_does_not_change_summary() -> None:
    timeline = TaskTimeline()
    timeline.record(view("Tarefa: iniciada · 0/4 etapas", False))
    timeline.record(view("Tarefa: falhou · 0/4 etapas", True))
    before = timeline.summary()
    timeline.display_interruptions()
    assert timeline.summary() == before
    assert len(timeline.snapshot()) == 2


def test_m146_host_checkbox_read_only_view_and_default(host) -> None:
    window, provider, _, dry = host
    assert window.task_timeline_interruptions_only.objectName() == "lyra_task_timeline_interruptions_only"
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.isReadOnly()
    assert window.task_timeline_view.toPlainText() == window._task_timeline.display()
    assert not dry.workers and provider.calls == 0


def test_m146_host_checkbox_toggles_display_not_state(host) -> None:
    window, provider, _, dry = host
    window._on_tool_state(LyraRunState.start("PRIVATE", max_steps=4))
    before = window._task_timeline.snapshot()
    summary = window.task_summary.text()
    window.task_timeline_interruptions_only.click()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window._task_timeline.snapshot() == before
    assert window.task_summary.text() == summary
    window.task_timeline_interruptions_only.click()
    assert "iniciada" in window.task_timeline_view.toPlainText()
    assert not dry.workers and provider.calls == 0


def test_m146_host_cancelled_then_filtered(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE", ())
    window._cancel_active_task()
    window.task_timeline_interruptions_only.setChecked(True)
    assert "cancelamento solicitado" in window.task_timeline_view.toPlainText()
    window._on_tool_state(LyraRunState.start("PRIVATE", max_steps=4).cancel("PRIVATE"))
    assert "cancelada" in window.task_timeline_view.toPlainText()
    assert "PRIVATE" not in window.task_timeline_view.toPlainText()
    assert len(dry.workers) == 1 and provider.calls == 0


def test_m146_host_direct_failure_only_with_matching_id(host) -> None:
    window, provider, _, dry = host
    request = ActionRequest(action="open_application", arguments={"path":"PRIVATE"})
    window._start_action(request)
    window.task_timeline_interruptions_only.setChecked(True)
    wrong = ActionRequest(action="open_application")
    window._on_action_result(ActionResult(request_id=wrong.request_id, success=False, message="PRIVATE"))
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    window._on_action_result(ActionResult(request_id=request.request_id, success=False, message="PRIVATE"))
    assert "falha reportada" in window.task_timeline_view.toPlainText()
    assert "PRIVATE" not in window.task_timeline_view.toPlainText()
    assert provider.calls == 0 and len(dry.workers) == 1


def test_m146_host_busy_filter_available_without_dispatch(host) -> None:
    window, provider, _, dry = host
    window._start_tool_task("PRIVATE", ())
    assert window.task_timeline_interruptions_only.isEnabled()
    window.task_timeline_interruptions_only.click()
    assert window.task_timeline_interruptions_only.isChecked()
    assert not window.input.isEnabled()
    assert len(dry.workers) == 1 and provider.calls == 0


def test_m146_host_two_windows_filter_isolation(host) -> None:
    window, provider, _, _ = host
    other_provider = ControlledProvider()
    other = MainWindow(ActionRegistry(), object(), other_provider, build_default_tool_catalog())  # type: ignore[arg-type]
    try:
        window.task_timeline_interruptions_only.setChecked(True)
        assert not other.task_timeline_interruptions_only.isChecked()
        assert provider.calls == other_provider.calls == 0
    finally:
        other.close()


def test_m146_host_denied_reset_preserves_filter(host, monkeypatch) -> None:
    window, provider, _, _ = host
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert window.task_timeline_interruptions_only.isChecked()
    assert provider.calls == 0


def test_m146_host_accepted_reset_clears_events_preserves_filter(host, monkeypatch) -> None:
    window, provider, memory, _ = host
    window._on_tool_state(LyraRunState.start("PRIVATE", max_steps=4).fail("PRIVATE"))
    window.task_timeline_interruptions_only.setChecked(True)
    assert "falhou" in window.task_timeline_view.toPlainText()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window.task_summary.text() == "Resumo: 0/12 eventos · sem registros"
    assert window._memory is memory and provider.calls == 0
