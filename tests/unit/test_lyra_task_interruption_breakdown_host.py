from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TASK_TIMELINE_LIMIT, TaskTimeline
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"
PROCESSING = "Tarefa: falha no processamento · efeito não comprovado"
INVALID = "Tarefa: resultado inválido · efeito não comprovado"
DIRECT = "Ação direta: falha reportada · open_application"
SUCCESS = "Ação direta: pós-condição verificada · open_application"


def _view(text: str, terminal: bool | None) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=text, terminal=terminal)


def _detail(pending: int, cancelled: int, failed: int) -> str:
    return f"Tipos: pendentes {pending} · canceladas {cancelled} · falhas {failed}"


def _record(timeline: TaskTimeline, *events: tuple[str, bool | None]) -> None:
    for label, terminal in events:
        assert timeline.record(_view(label, terminal))


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
    pool = DryPool()
    window._pool = pool  # type: ignore[assignment]
    try:
        yield window, provider, memory, pool
    finally:
        window.close()


def test_m150_empty_model_has_fixed_safe_breakdown():
    timeline = TaskTimeline()
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)
    assert timeline.interruption_count_label() == "Interrupções: 0/12 eventos recentes"


def test_m150_pending_request_is_not_a_confirmed_cancellation():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False))
    assert timeline.interruption_breakdown_label() == _detail(1, 0, 0)


def test_m150_confirmed_cancellation_has_own_category():
    timeline = TaskTimeline()
    _record(timeline, (CANCELLED, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 1, 0)


def test_m150_workflow_failure_is_classified_as_failed():
    timeline = TaskTimeline()
    _record(timeline, (FAILED, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 1)


def test_m150_processing_failure_classified():
    timeline = TaskTimeline()
    _record(timeline, (PROCESSING, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 1)


def test_m150_invalid_result_classified_as_failed_not_effect_proof():
    timeline = TaskTimeline()
    _record(timeline, (INVALID, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 1)


def test_m150_direct_action_failure_classified():
    timeline = TaskTimeline()
    _record(timeline, (DIRECT, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 1)


def test_m150_verified_direct_success_excluded():
    timeline = TaskTimeline()
    _record(timeline, (SUCCESS, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_nonterminal_started_excluded():
    timeline = TaskTimeline()
    _record(timeline, ("Tarefa: iniciada · 0/4 etapas", False))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_untrusted_text_with_cancelled_prefix_excluded():
    timeline = TaskTimeline()
    _record(timeline, ("Tarefa: cancelada · FORGED", True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_nonterminal_failure_looking_text_excluded():
    timeline = TaskTimeline()
    _record(timeline, (FAILED, False))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_all_categories_combined_match_original_count():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False), (CANCELLED, True), (FAILED, True))
    assert timeline.interruption_breakdown_label() == _detail(1, 1, 1)
    assert timeline.interruption_count_label() == "Interrupções: 3/12 eventos recentes"


def test_m150_repeated_cancel_request_not_inflated():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False))
    assert not timeline.record(_view(PENDING, False))
    assert timeline.interruption_breakdown_label() == _detail(1, 0, 0)


def test_m150_same_label_terminal_promotion_reclassifies():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False))
    assert timeline.record(_view(PENDING, True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)
    assert timeline.interruption_count_label() == "Interrupções: 0/12 eventos recentes"


def test_m150_terminal_downgrade_is_rejected():
    timeline = TaskTimeline()
    _record(timeline, (FAILED, True))
    assert not timeline.record(_view(FAILED, False))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 1)


def test_m150_rolling_window_evicts_pending_category():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False))
    for index in range(TASK_TIMELINE_LIMIT):
        timeline.record(_view(f"Tarefa: etapa {index}", False))
    assert len(timeline.snapshot()) == TASK_TIMELINE_LIMIT
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_rolling_window_evicts_confirmed_category():
    timeline = TaskTimeline()
    _record(timeline, (CANCELLED, True))
    for index in range(TASK_TIMELINE_LIMIT):
        timeline.record(_view(f"Tarefa: etapa {index}", False))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_rolling_window_evicts_failed_category():
    timeline = TaskTimeline()
    _record(timeline, (FAILED, True))
    for index in range(TASK_TIMELINE_LIMIT):
        timeline.record(_view(f"Tarefa: etapa {index}", False))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_twelve_bounded_failures_are_all_failed():
    timeline = TaskTimeline()
    for index in range(20):
        assert timeline.record(_view(f"Ação direta: falha reportada · action_{index}", True))
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 12)
    assert timeline.interruption_count_label() == "Interrupções: 12/12 eventos recentes"


def test_m150_clear_resets_category_breakdown():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False), (CANCELLED, True))
    timeline.clear()
    assert timeline.interruption_breakdown_label() == _detail(0, 0, 0)


def test_m150_repeated_read_only_breakdown_never_changes_history():
    timeline = TaskTimeline()
    _record(timeline, (PENDING, False), (FAILED, True))
    before = timeline.snapshot(), timeline.summary(), timeline.display()
    for _ in range(5):
        assert timeline.interruption_breakdown_label() == _detail(1, 0, 1)
    assert (timeline.snapshot(), timeline.summary(), timeline.display()) == before


def test_m150_qt_label_default_visible_with_panel_hidden(host):
    window, _, _, _ = host
    assert window.task_interruption_breakdown.objectName() == "lyra_task_interruption_breakdown"
    assert window.task_interruption_breakdown.text() == _detail(0, 0, 0)
    assert not window.task_interruption_breakdown.isHidden()
    assert window.task_timeline_view.isHidden()


def test_m150_qt_model_refresh_shows_three_categories(host):
    window, _, _, _ = host
    _record(window._task_timeline, (PENDING, False), (CANCELLED, True), (FAILED, True))
    window._refresh_task_timeline()
    assert window.task_interruption_breakdown.text() == _detail(1, 1, 1)
    assert window.task_interruption_count.text() == "Interrupções: 3/12 eventos recentes"


def test_m150_qt_filter_toggling_preserves_breakdown(host):
    window, _, _, _ = host
    _record(window._task_timeline, (PENDING, False), (FAILED, True))
    window._refresh_task_timeline()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_interruption_breakdown.text() == _detail(1, 0, 1)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_interruption_breakdown.text() == _detail(1, 0, 1)


def test_m150_qt_panel_toggle_preserves_breakdown(host):
    window, _, _, _ = host
    _record(window._task_timeline, (CANCELLED, True))
    window._refresh_task_timeline()
    for _ in range(2):
        window.task_timeline_toggle_shortcut.activated.emit()
        assert window.task_interruption_breakdown.text() == _detail(0, 1, 0)


def test_m150_qt_denied_reset_does_not_change_breakdown(host, monkeypatch):
    window, _, _, _ = host
    _record(window._task_timeline, (FAILED, True))
    window._refresh_task_timeline()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert window.task_interruption_breakdown.text() == _detail(0, 0, 1)


def test_m150_qt_accepted_reset_clears_breakdown_preserves_filter(host, monkeypatch):
    window, provider, memory, pool = host
    _record(window._task_timeline, (PENDING, False), (CANCELLED, True))
    window._refresh_task_timeline()
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window.task_interruption_breakdown.text() == _detail(0, 0, 0)
    assert window.task_timeline_interruptions_only.isChecked()
    assert window._memory is memory and provider.calls == 0 and not pool.workers


def test_m150_qt_two_windows_isolated(host):
    window, _, _, _ = host
    other = MainWindow(ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog())
    try:
        _record(window._task_timeline, (FAILED, True))
        window._refresh_task_timeline()
        assert window.task_interruption_breakdown.text() == _detail(0, 0, 1)
        assert other.task_interruption_breakdown.text() == _detail(0, 0, 0)
    finally:
        other.close()


def test_m150_qt_refresh_does_not_dispatch_or_mutate_memory(host):
    window, provider, memory, pool = host
    for _ in range(6):
        window._refresh_task_timeline()
    assert window.task_interruption_breakdown.text() == _detail(0, 0, 0)
    assert window._memory is memory and provider.calls == 0 and not pool.workers
