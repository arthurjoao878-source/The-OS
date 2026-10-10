from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import ExecutionControl
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import (
    TASK_TIMELINE_INTERRUPTIONS_EMPTY,
    TASK_TIMELINE_LIMIT,
    TaskTimeline,
)
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"
PROCESSING = "Tarefa: falha no processamento · efeito não comprovado"
INVALID = "Tarefa: resultado inválido · efeito não comprovado"
DIRECT = "Ação direta: falha reportada · open_application"
START = "Tarefa: iniciada · 0/4 etapas"
SUCCESS = "Ação direta: pós-condição verificada · open_application"


def _view(text: str, terminal: bool) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=text, terminal=terminal)


def _populate(timeline: TaskTimeline) -> None:
    for text, terminal in (
        (START, False),
        (PENDING, False),
        (CANCELLED, True),
        (FAILED, True),
        (PROCESSING, True),
        (INVALID, True),
        (DIRECT, True),
        (SUCCESS, True),
    ):
        assert timeline.record(_view(text, terminal))


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("not authorized")

    def reply(self, text, *, history=()):
        raise AssertionError("not authorized")


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


def test_m151_model_all_preserves_m146_view_and_numbering():
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.display_interruption_category("all") == timeline.display_interruptions()
    assert timeline.display_interruption_category("all").startswith("2. " + PENDING)
    assert "8. " + SUCCESS not in timeline.display_interruption_category("all")


@pytest.mark.parametrize(
    ("category", "expected"),
    [("pending", "2. " + PENDING), ("cancelled", "3. " + CANCELLED)],
)
def test_m151_model_category_single_event(category, expected):
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.display_interruption_category(category) == expected


def test_m151_model_failure_category_includes_only_three_plus_direct():
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.display_interruption_category("failed").splitlines() == [
        "4. " + FAILED,
        "5. " + PROCESSING,
        "6. " + INVALID,
        "7. " + DIRECT,
    ]


def test_m151_model_read_only_preserves_summary_and_counts():
    timeline = TaskTimeline()
    _populate(timeline)
    baseline = timeline.snapshot(), timeline.summary(), timeline.display(), timeline.interruption_count_label(), timeline.interruption_breakdown_label()
    for category in ("all", "pending", "cancelled", "failed"):
        for _ in range(3):
            timeline.display_interruption_category(category)
    assert (timeline.snapshot(), timeline.summary(), timeline.display(), timeline.interruption_count_label(), timeline.interruption_breakdown_label()) == baseline
    assert timeline.interruption_count_label() == "Interrupções: 6/12 eventos recentes"


@pytest.mark.parametrize("invalid", [None, True, False, 0, 1, "", "private", "ALL", "failed\n", [], {}])
def test_m151_invalid_category_fails_closed(invalid):
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.display_interruption_category(invalid) == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m151_untrusted_status_and_nonterminal_failure_never_leak():
    timeline = TaskTimeline()
    for text, terminal in (
        ("Tarefa: cancelada · SECRET", True),
        ("Ação direta: falha reportada · C:/PRIVATE", True),
        (FAILED, False),
    ):
        assert timeline.record(_view(text, terminal))
    for category in ("pending", "cancelled", "failed", "all"):
        assert timeline.display_interruption_category(category) == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m151_duplicate_and_terminal_promotion_inherited():
    timeline = TaskTimeline()
    assert timeline.record(_view(PENDING, False))
    assert not timeline.record(_view(PENDING, False))
    assert timeline.display_interruption_category("pending") == "1. " + PENDING
    assert timeline.record(_view(PENDING, True))
    assert timeline.display_interruption_category("pending") == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert timeline.interruption_count_label() == "Interrupções: 0/12 eventos recentes"


def test_m151_twelve_event_eviction_and_clear_are_bounded():
    timeline = TaskTimeline()
    assert timeline.record(_view(CANCELLED, True))
    for i in range(20):
        assert timeline.record(_view(f"Tarefa: etapa {i}", False))
    assert len(timeline.snapshot()) == TASK_TIMELINE_LIMIT
    assert timeline.display_interruption_category("cancelled") == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert timeline.display_interruption_category("all") == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    timeline.clear()
    assert timeline.snapshot() == ()
    assert timeline.display_interruption_category("failed") == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m151_qt_selector_is_finite_and_defaults_to_all(host):
    window, provider, _, dry = host
    widget = window.task_timeline_interruption_category
    assert widget.objectName() == "lyra_task_timeline_interruption_category"
    assert widget.count() == 4
    assert tuple(widget.itemData(i) for i in range(4)) == (
        "all", "pending", "cancelled", "failed"
    )
    assert tuple(widget.itemText(i) for i in range(4)) == (
        "Todas", "Pendentes", "Canceladas", "Falhas"
    )
    assert widget.currentData() == "all"
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0 and not dry.workers


def test_m151_qt_category_only_applies_when_interruption_filter_on(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    full = window.task_timeline_view.toPlainText()
    window.task_timeline_interruption_category.setCurrentIndex(3)
    assert window.task_timeline_view.toPlainText() == full
    window.task_timeline_interruptions_only.setChecked(True)
    assert window.task_timeline_view.toPlainText().splitlines() == [
        "4. " + FAILED, "5. " + PROCESSING, "6. " + INVALID, "7. " + DIRECT
    ]
    window.task_timeline_interruptions_only.setChecked(False)
    assert window.task_timeline_view.toPlainText() == full


def test_m151_qt_category_changes_do_not_change_counter_or_draft(host):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window.input.setText("rascunho mantido")
    window.task_timeline_interruptions_only.setChecked(True)
    before = window._task_timeline.snapshot()
    for index in range(4):
        window.task_timeline_interruption_category.setCurrentIndex(index)
        assert window.task_interruption_count.text() == "Interrupções: 6/12 eventos recentes"
        assert window.task_interruption_breakdown.text() == (
            "Tipos: pendentes 1 · canceladas 1 · falhas 4"
        )
        assert window._task_timeline.snapshot() == before
    assert window.input.text() == "rascunho mantido"
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m151_qt_ctrl_shift_i_roundtrip_reuses_category(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruption_category.setCurrentIndex(1)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == window._task_timeline.display()
    assert window.task_timeline_interruption_category.currentData() == "pending"


def test_m151_qt_real_key_filter_shortcut_if_visible(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        window.input,
        Qt.Key.Key_I,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == "3. " + CANCELLED


def test_m151_qt_panel_shortcut_remains_read_only(host):
    window, _, _, _ = host
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()


def test_m151_qt_invalid_combo_data_fails_closed(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.addItem("Privado", "unsafe-private-data")
    window.task_timeline_interruption_category.setCurrentIndex(4)
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window._task_timeline.snapshot()[1] == PENDING


def test_m151_qt_denied_reset_preserves_category_and_history(host, monkeypatch):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert window.task_timeline_interruption_category.currentData() == "pending"
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING


def test_m151_qt_accepted_reset_clears_events_but_preserves_category(host, monkeypatch):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window.task_timeline_interruption_category.currentData() == "cancelled"
    assert window.task_timeline_interruptions_only.isChecked()
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m151_qt_two_windows_isolated(host):
    window, _, _, _ = host
    other = MainWindow(ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog())
    try:
        _populate(window._task_timeline)
        _populate(other._task_timeline)
        window.task_timeline_interruption_category.setCurrentIndex(1)
        window.task_timeline_interruptions_only.setChecked(True)
        other.task_timeline_interruption_category.setCurrentIndex(3)
        other.task_timeline_interruptions_only.setChecked(True)
        assert window.task_timeline_view.toPlainText() == "2. " + PENDING
        assert other.task_timeline_view.toPlainText().startswith("4. " + FAILED)
        assert window.task_timeline_interruption_category.currentData() == "pending"
        assert other.task_timeline_interruption_category.currentData() == "failed"
    finally:
        other.close()


def test_m151_qt_busy_dry_control_keeps_read_only_category_filter(host):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window._active_control = ExecutionControl()
    window._set_busy(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    assert window.task_timeline_view.toPlainText().startswith("4. " + FAILED)
    assert window.task_timeline_view.isReadOnly()
    assert window._memory is memory and provider.calls == 0 and not dry.workers
    window._active_control = None
    window._set_busy(False)


def test_m151_qt_new_dry_task_clears_old_entries_retains_category(host):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.task_timeline_interruptions_only.setChecked(True)
    window._start_tool_task("test controlled", ())
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window.task_timeline_interruption_category.currentData() == "cancelled"
    assert provider.calls == 0 and len(dry.workers) == 1 and window._memory is memory
    window._active_control = None
    window._set_busy(False)
