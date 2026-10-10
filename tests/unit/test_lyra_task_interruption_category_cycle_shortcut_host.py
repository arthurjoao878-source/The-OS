from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import ExecutionControl
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TASK_TIMELINE_INTERRUPTIONS_EMPTY
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"
START = "Tarefa: iniciada · 0/4 etapas"
CATEGORIES = ("all", "pending", "cancelled", "failed")
LABELS = ("Todas", "Pendentes", "Canceladas", "Falhas")


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("provider continuation prohibited")

    def reply(self, text, *, history=()):
        raise AssertionError("provider reply prohibited")


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


def _populate(window: MainWindow) -> None:
    for text, terminal in (
        (START, False), (PENDING, False), (CANCELLED, True), (FAILED, True)
    ):
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=text, terminal=terminal)
        )
    window._refresh_task_timeline()


def _press(window: MainWindow, widget) -> None:
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    widget.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        widget, Qt.Key.Key_Y,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m152_qt_shortcut_identity_sequence_and_scope(host):
    window, provider, _, dry = host
    shortcut = window.task_timeline_interruption_category_cycle_shortcut
    assert shortcut.objectName() == "lyra_task_timeline_interruption_category_cycle_shortcut"
    assert shortcut.key() == QKeySequence("Ctrl+Shift+Y")
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.parent() is window
    assert shortcut.isEnabled()
    assert provider.calls == 0 and not dry.workers


def test_m152_qt_default_finite_model_and_initial_category(host):
    window, _, _, _ = host
    combo = window.task_timeline_interruption_category
    assert combo.count() == 4
    assert tuple(combo.itemData(i) for i in range(4)) == CATEGORIES
    assert tuple(combo.itemText(i) for i in range(4)) == LABELS
    assert combo.currentIndex() == 0
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m152_qt_signal_cycles_four_choices_and_wraps(host):
    window, _, _, _ = host
    shortcut = window.task_timeline_interruption_category_cycle_shortcut
    combo = window.task_timeline_interruption_category
    for category in (*CATEGORIES[1:], CATEGORIES[0]):
        shortcut.activated.emit()
        assert combo.currentData() == category
    assert combo.currentIndex() == 0


def test_m152_qt_direct_handler_same_cycle_as_signal(host):
    window, _, _, _ = host
    window._cycle_task_timeline_interruption_category_shortcut()
    assert window.task_timeline_interruption_category.currentData() == "pending"
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_interruption_category.currentData() == "cancelled"


def test_m152_qt_real_key_composer_cycles(host):
    window, provider, memory, dry = host
    window.input.setText("rascunho preservado")
    _press(window, window.input)
    assert window.task_timeline_interruption_category.currentData() == "pending"
    _press(window, window.input)
    assert window.task_timeline_interruption_category.currentData() == "cancelled"
    assert window.input.text() == "rascunho preservado"
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m152_qt_real_key_find_preserves_query_and_draft(host):
    window, _, _, _ = host
    window.input.setText("rascunho")
    window.transcript_find.setText("palavra")
    _press(window, window.transcript_find)
    assert window.task_timeline_interruption_category.currentData() == "pending"
    assert window.transcript_find.text() == "palavra"
    assert window.input.text() == "rascunho"


def test_m152_qt_real_key_read_only_transcript(host):
    window, _, _, _ = host
    _press(window, window.chat)
    assert window.chat.isReadOnly()
    assert window.task_timeline_interruption_category.currentData() == "pending"


def test_m152_qt_cycle_is_inert_to_full_history_when_filter_off(host):
    window, _, _, _ = host
    _populate(window)
    before = window.task_timeline_view.toPlainText()
    for _ in range(4):
        window._cycle_task_timeline_interruption_category_shortcut()
        assert window.task_timeline_view.toPlainText() == before
        assert window._task_timeline.snapshot()[0] == START


def test_m152_qt_cycle_narrows_existing_filter_and_preserves_numbering(host):
    window, _, _, _ = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    expected = (
        window._task_timeline.display_interruptions(),
        "2. " + PENDING,
        "3. " + CANCELLED,
        "4. " + FAILED,
        window._task_timeline.display_interruptions(),
    )
    assert window.task_timeline_view.toPlainText() == expected[0]
    for value in expected[1:]:
        window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
        assert window.task_timeline_view.toPlainText() == value


def test_m152_qt_cycle_preserves_m149_m150_counters_and_summary(host):
    window, _, _, _ = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    original = (
        window._task_timeline.snapshot(), window.task_summary.text(),
        window.task_interruption_count.text(), window.task_interruption_breakdown.text(),
    )
    for _ in range(12):
        window._cycle_task_timeline_interruption_category_shortcut()
        assert (
            window._task_timeline.snapshot(), window.task_summary.text(),
            window.task_interruption_count.text(), window.task_interruption_breakdown.text(),
        ) == original


def test_m152_qt_compatibility_filter_and_panel_shortcuts(host):
    window, _, _, _ = host
    _populate(window)
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    window.task_timeline_toggle_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentData() == "pending"


def test_m152_qt_disabled_shortcut_guard(host):
    window, _, _, _ = host
    shortcut = window.task_timeline_interruption_category_cycle_shortcut
    shortcut.setEnabled(False)
    window._cycle_task_timeline_interruption_category_shortcut()
    assert window.task_timeline_interruption_category.currentData() == "all"


def test_m152_qt_disabled_selector_guard(host):
    window, _, _, _ = host
    window.task_timeline_interruption_category.setEnabled(False)
    window._cycle_task_timeline_interruption_category_shortcut()
    assert window.task_timeline_interruption_category.currentData() == "all"


@pytest.mark.parametrize("changed", ("data", "text", "extra", "removed"))
def test_m152_qt_corrupt_finite_selector_fails_closed(host, changed):
    window, _, _, _ = host
    combo = window.task_timeline_interruption_category
    if changed == "data":
        combo.setItemData(0, "private")
    elif changed == "text":
        combo.setItemText(1, "Privado")
    elif changed == "extra":
        combo.addItem("Secret", "private")
    else:
        combo.removeItem(3)
    before = combo.currentIndex()
    window._cycle_task_timeline_interruption_category_shortcut()
    assert combo.currentIndex() == before


def test_m152_qt_invalid_negative_current_index_fails_closed(host):
    window, _, _, _ = host
    combo = window.task_timeline_interruption_category
    combo.setCurrentIndex(-1)
    window._cycle_task_timeline_interruption_category_shortcut()
    assert combo.currentIndex() == -1


def test_m152_qt_corrupt_category_with_filtered_view_is_safe(host):
    window, _, _, _ = host
    _populate(window)
    combo = window.task_timeline_interruption_category
    window.task_timeline_interruptions_only.setChecked(True)
    combo.setItemData(0, "RAW")
    window._refresh_task_timeline()
    window._cycle_task_timeline_interruption_category_shortcut()
    assert combo.currentData() == "RAW"
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY


def test_m152_qt_busy_shortcut_cycle_preserves_dry_worker(host):
    window, provider, memory, dry = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window._active_control = ExecutionControl()
    window._set_busy(True)
    assert window.task_timeline_interruption_category.isEnabled()
    assert window.task_timeline_interruption_category_cycle_shortcut.isEnabled()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING
    assert window._memory is memory and provider.calls == 0 and not dry.workers
    window._active_control = None
    window._set_busy(False)


def test_m152_qt_real_key_busy_keeps_read_only_filter(host):
    window, provider, _, dry = host
    _populate(window)
    window._active_control = ExecutionControl()
    window._set_busy(True)
    window.task_timeline_interruptions_only.setChecked(True)
    _press(window, window.chat)
    assert window.task_timeline_interruption_category.currentData() == "pending"
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING
    assert provider.calls == 0 and not dry.workers
    window._active_control = None
    window._set_busy(False)


def test_m152_qt_two_window_state_and_key_isolation(host):
    window, _, _, _ = host
    other = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        _populate(window)
        _populate(other)
        _press(window, window.input)
        assert window.task_timeline_interruption_category.currentData() == "pending"
        assert other.task_timeline_interruption_category.currentData() == "all"
        other.task_timeline_interruption_category_cycle_shortcut.activated.emit()
        other.task_timeline_interruption_category_cycle_shortcut.activated.emit()
        assert other.task_timeline_interruption_category.currentData() == "cancelled"
        assert window.task_timeline_interruption_category.currentData() == "pending"
    finally:
        other.close()


def test_m152_qt_denied_reset_preserves_selection_and_history(host, monkeypatch):
    window, _, _, _ = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window._cycle_task_timeline_interruption_category_shortcut()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    assert window.task_timeline_interruption_category.currentData() == "pending"
    assert window.task_timeline_view.toPlainText() == "2. " + PENDING


def test_m152_qt_accepted_reset_clears_events_retains_shortcut(host, monkeypatch):
    window, provider, memory, dry = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window._cycle_task_timeline_interruption_category_shortcut()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert window.task_timeline_interruption_category.currentData() == "pending"
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_interruption_category.currentData() == "cancelled"
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m152_qt_new_dry_task_resets_events_not_category(host):
    window, provider, memory, dry = host
    _populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    window._start_tool_task("controlled", ())
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_interruption_category.currentData() == "pending"
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_INTERRUPTIONS_EMPTY
    assert len(dry.workers) == 1 and provider.calls == 0 and window._memory is memory
    window._active_control = None
    window._set_busy(False)


def test_m152_qt_shortcut_no_provider_action_memory_or_new_authority(host):
    window, provider, memory, dry = host
    _populate(window)
    before = window._task_timeline.snapshot()
    for _ in range(20):
        window._cycle_task_timeline_interruption_category_shortcut()
    assert window._task_timeline.snapshot() == before
    assert window._memory is memory and provider.calls == 0 and not dry.workers
    assert window.chat.isReadOnly()
