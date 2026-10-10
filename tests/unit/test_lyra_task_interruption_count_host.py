from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TASK_TIMELINE_LIMIT, TaskTimeline
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
        raise AssertionError("continuation not authorized")

    def reply(self, text, *, history=()):
        raise AssertionError("reply not authorized")


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


def _view(text: str, terminal: bool | None) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=text, terminal=terminal)


def _count(n: int) -> str:
    return f"Interrupções: {n}/{TASK_TIMELINE_LIMIT} eventos recentes"


def test_m149_empty_count_is_fixed_and_bounded() -> None:
    assert TaskTimeline().interruption_count_label() == _count(0)


def test_m149_nonterminal_start_does_not_increment() -> None:
    timeline = TaskTimeline()
    assert timeline.record(_view("Tarefa: iniciada · 0/4 etapas", False))
    assert timeline.interruption_count_label() == _count(0)


def test_m149_cancel_request_is_presented_as_interruption_not_terminal() -> None:
    timeline = TaskTimeline()
    assert timeline.record(_view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    assert timeline.interruption_count_label() == _count(1)
    assert "cancelamento pendente" in timeline.summary()


def test_m149_confirmed_cancellation_increments_separately() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    timeline.record(_view("Tarefa: cancelada · 0/4 etapas", True))
    assert timeline.interruption_count_label() == _count(2)


def test_m149_workflow_failure_counts() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: falhou · 1/4 etapas · sistema", True))
    assert timeline.interruption_count_label() == _count(1)


def test_m149_processing_failure_counts() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: falha no processamento · efeito não comprovado", True))
    assert timeline.interruption_count_label() == _count(1)


def test_m149_invalid_result_counts() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: resultado inválido · efeito não comprovado", True))
    assert timeline.interruption_count_label() == _count(1)


def test_m149_safe_direct_failure_counts() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Ação direta: falha reportada · open_application", True))
    assert timeline.interruption_count_label() == _count(1)


def test_m149_success_or_unverified_dispatch_not_counted() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Ação direta: resultado recebido, efeito não comprovado · open_application", True))
    timeline.record(_view("Ação direta: efeito despachado, pós-condição não comprovada · open_application", True))
    timeline.record(_view("Ação direta: pós-condição verificada · open_application", True))
    assert timeline.interruption_count_label() == _count(0)


def test_m149_fake_interruption_label_fails_closed() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: falhou · PRIVATE_ARGUMENT", True))
    timeline.record(_view("Ação direta: falha reportada · C:/PRIVATE", True))
    assert timeline.interruption_count_label() == _count(0)


def test_m149_nonterminal_failure_label_is_not_counted() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: falha no processamento · efeito não comprovado", False))
    assert timeline.interruption_count_label() == _count(0)


def test_m149_duplicate_terminal_does_not_double_count() -> None:
    timeline = TaskTimeline()
    failure = _view("Tarefa: falha no processamento · efeito não comprovado", True)
    assert timeline.record(failure)
    assert not timeline.record(failure)
    assert timeline.interruption_count_label() == _count(1)


def test_m149_same_label_terminal_upgrade_reclassifies_once() -> None:
    timeline = TaskTimeline()
    pending = "Tarefa: cancelamento solicitado · aguardando confirmação"
    assert timeline.record(_view(pending, False))
    assert timeline.interruption_count_label() == _count(1)
    assert timeline.record(_view(pending, True))
    assert timeline.interruption_count_label() == _count(0)
    assert len(timeline.snapshot()) == 1


def test_m149_terminal_downgrade_rejected() -> None:
    timeline = TaskTimeline()
    failure = "Tarefa: falha no processamento · efeito não comprovado"
    timeline.record(_view(failure, True))
    assert not timeline.record(_view(failure, False))
    assert timeline.interruption_count_label() == _count(1)


def test_m149_rolling_eviction_decrements_count() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: falha no processamento · efeito não comprovado", True))
    for i in range(12):
        timeline.record(_view(f"Tarefa: etapa {i}", False))
    assert len(timeline.snapshot()) == 12
    assert timeline.interruption_count_label() == _count(0)


def test_m149_count_never_exceeds_twelve() -> None:
    timeline = TaskTimeline()
    for i in range(30):
        timeline.record(_view(f"Ação direta: falha reportada · action_{i}", True))
    assert timeline.interruption_count_label() == _count(12)
    assert len(timeline.snapshot()) == 12


def test_m149_count_is_read_only_and_filter_independent() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: iniciada · 0/4 etapas", False))
    timeline.record(_view("Tarefa: cancelada · 0/4 etapas", True))
    before = timeline.snapshot(), timeline.summary(), timeline.display()
    for _ in range(5):
        assert timeline.interruption_count_label() == _count(1)
        assert "2. Tarefa: cancelada" in timeline.display_interruptions()
    assert (timeline.snapshot(), timeline.summary(), timeline.display()) == before


def test_m149_clear_resets_count() -> None:
    timeline = TaskTimeline()
    timeline.record(_view("Tarefa: resultado inválido · efeito não comprovado", True))
    timeline.clear()
    assert timeline.interruption_count_label() == _count(0)


def test_m149_qt_label_identity_default_visible_when_panel_hidden(host) -> None:
    window, _, _, _ = host
    assert window.task_interruption_count.objectName() == "lyra_task_interruption_count"
    assert window.task_interruption_count.text() == _count(0)
    assert window.task_timeline_view.isHidden()
    assert not window.task_interruption_count.isHidden()


def test_m149_qt_real_record_refresh_updates_count(host) -> None:
    window, _, _, _ = host
    window._on_tool_state(LyraRunState.start("PRIVATE_INTENT", max_steps=4))
    assert window.task_interruption_count.text() == _count(0)
    window._task_timeline.record(_view("Tarefa: falha no processamento · efeito não comprovado", True))
    window._refresh_task_timeline()
    assert window.task_interruption_count.text() == _count(1)
    assert "PRIVATE_INTENT" not in window.task_interruption_count.text()


def test_m149_qt_filter_keeps_count_stable(host) -> None:
    window, _, _, _ = host
    window._task_timeline.record(_view("Tarefa: cancelada · 0/4 etapas", True))
    window._refresh_task_timeline()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_interruption_count.text() == _count(1)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_interruption_count.text() == _count(1)


def test_m149_qt_panel_roundtrip_keeps_count(host) -> None:
    window, _, _, _ = host
    window._task_timeline.record(_view("Tarefa: cancelamento solicitado · aguardando confirmação", False))
    window._refresh_task_timeline()
    window.task_timeline_toggle_shortcut.activated.emit()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_interruption_count.text() == _count(1)
    assert window.task_timeline_view.isHidden()


def test_m149_qt_denied_reset_keeps_count(host, monkeypatch) -> None:
    window, _, _, _ = host
    window._task_timeline.record(_view("Tarefa: resultado inválido · efeito não comprovado", True))
    window._refresh_task_timeline()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert window.task_interruption_count.text() == _count(1)


def test_m149_qt_accepted_reset_clears_count_only(host, monkeypatch) -> None:
    window, provider, memory, dry = host
    window._task_timeline.record(_view("Tarefa: resultado inválido · efeito não comprovado", True))
    window._refresh_task_timeline()
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window.task_interruption_count.text() == _count(0)
    assert window.task_timeline_interruptions_only.isChecked()
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m149_qt_two_windows_count_isolation(host) -> None:
    window, _, _, _ = host
    other = MainWindow(ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog())
    try:
        window._task_timeline.record(_view("Tarefa: cancelada · 0/4 etapas", True))
        window._refresh_task_timeline()
        assert window.task_interruption_count.text() == _count(1)
        assert other.task_interruption_count.text() == _count(0)
    finally:
        other.close()


def test_m149_qt_busy_task_counter_is_passive(host) -> None:
    window, provider, memory, dry = host
    window._start_tool_task("PRIVATE_TASK", ())
    assert len(dry.workers) == 1
    control = window._active_control
    window._refresh_task_timeline()
    assert window.task_interruption_count.text() == _count(0)
    assert window._active_control is control
    assert len(dry.workers) == 1 and provider.calls == 0 and window._memory is memory


def test_m149_qt_new_task_restarts_counter(host) -> None:
    window, _, _, dry = host
    window._task_timeline.record(_view("Tarefa: falha no processamento · efeito não comprovado", True))
    window._refresh_task_timeline()
    assert window.task_interruption_count.text() == _count(1)
    window._start_tool_task("PRIVATE_TASK", ())
    assert window.task_interruption_count.text() == _count(0)
    assert len(dry.workers) == 1


def test_m149_qt_no_new_authority_memory_or_provider(host) -> None:
    window, provider, memory, dry = host
    for _ in range(10):
        window._refresh_task_timeline()
    assert window.task_interruption_count.text() == _count(0)
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers
    assert window._active_control is None and window._active_direct_action is None
