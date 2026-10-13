from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView


class ControlledProvider:
    provider_id = "controlled"

    def __init__(self):
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="unexpected", provider_id="controlled")

    def continue_after_tools(self, turn, results):
        raise AssertionError("provider continuation forbidden")

    def reply(self, text, *, history=()):
        raise AssertionError("provider reply forbidden")


class DryPool:
    def __init__(self):
        self.workers = []

    def start(self, worker):
        self.workers.append(worker)


@pytest.fixture
def host():
    app = QApplication.instance() or QApplication([])
    _ = app
    provider = ControlledProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory, provider, build_default_tool_catalog()
    )
    pool = DryPool()
    window._pool = pool
    try:
        yield window, provider, memory, pool
    finally:
        window.close()


def populate(window):
    for index in range(12):
        message, terminal = (
            ("Tarefa: iniciada · 0/4 etapas", False),
            ("Tarefa: cancelamento solicitado · aguardando confirmação", False),
            ("Tarefa: cancelada · 0/4 etapas", True),
            ("Tarefa: falhou · 1/4 etapas · sistema", True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=message, terminal=terminal)
        )
    window._refresh_task_timeline()
    window.show()
    QApplication.processEvents()


def snapshot(window):
    t = window._task_timeline
    return (
        t.snapshot(), t.summary(), t.interruption_count_label(),
        t.interruption_breakdown_label(),
        window.task_timeline_interruptions_only.isChecked(),
        window.task_timeline_interruption_category.currentIndex(),
        window.task_timeline_interruption_category.currentData(),
        window.task_timeline_view.toPlainText(),
        window.input.text(), window.transcript_find.text(),
        window.chat.toPlainText(),
    )


def passive(window, provider, memory, pool, state):
    assert snapshot(window) == state
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert not pool.workers


def press_shift_return(window, target=None):
    widget = window.task_timeline_find_query if target is None else target
    window.activateWindow()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert widget.hasFocus()
    QTest.keyClick(widget, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QApplication.processEvents()


def selected(window):
    c = window.task_timeline_view.textCursor()
    return (c.selectionStart(), c.selectionEnd(), c.selectedText())


def prepare(window, query="falhou"):
    populate(window)
    window.task_timeline_find_query.setText(query)
    QApplication.processEvents()
    return snapshot(window)


def test_m175_identity_widget_context_default(host):
    window, provider, memory, pool = host
    shortcut = window.task_timeline_find_previous_shortcut
    assert isinstance(shortcut, QShortcut)
    assert shortcut.key() == QKeySequence("Shift+Return")
    assert shortcut.objectName() == "lyra_task_timeline_find_previous_shortcut"
    assert shortcut.parent() is window.task_timeline_find_query
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    assert shortcut.isEnabled()
    passive(window, provider, memory, pool, snapshot(window))


def test_m175_real_key_previous_from_end(host):
    window, provider, memory, pool = host
    before = prepare(window)
    assert window.task_timeline_view.isHidden()
    press_shift_return(window)
    assert not window.task_timeline_view.isHidden()
    assert selected(window)[2].lower() == "falhou"
    assert window.task_timeline_find_position.text() == "Atual: 3"
    passive(window, provider, memory, pool, before)


def test_m175_real_key_repeat_previous(host):
    window, provider, memory, pool = host
    before = prepare(window)
    press_shift_return(window)
    assert window.task_timeline_find_position.text() == "Atual: 3"
    press_shift_return(window)
    assert window.task_timeline_find_position.text() == "Atual: 2"
    press_shift_return(window)
    assert window.task_timeline_find_position.text() == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m175_real_key_wrap_from_first_to_last(host):
    window, provider, memory, pool = host
    before = prepare(window)
    window.task_timeline_find_next.click()
    assert window.task_timeline_find_position.text() == "Atual: 1"
    press_shift_return(window)
    assert window.task_timeline_find_position.text() == "Atual: 3"
    passive(window, provider, memory, pool, before)


def test_m175_enter_next_compatibility(host):
    window, provider, memory, pool = host
    before = prepare(window)
    window.task_timeline_find_previous.click()
    assert window.task_timeline_find_position.text() == "Atual: 3"
    widget = window.task_timeline_find_query
    widget.setFocus()
    QApplication.processEvents()
    QTest.keyClick(widget, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert window.task_timeline_find_position.text() == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m175_shift_return_and_next_inverse(host):
    window, provider, memory, pool = host
    before = prepare(window)
    window.task_timeline_find_next.click()
    first = selected(window)
    window.task_timeline_find_next.click()
    assert window.task_timeline_find_position.text() == "Atual: 2"
    press_shift_return(window)
    assert selected(window) == first
    assert window.task_timeline_find_position.text() == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m175_empty_query_fail_closed(host):
    window, provider, memory, pool = host
    before = prepare(window, "")
    old = selected(window)
    press_shift_return(window)
    assert selected(window) == old
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_find_position.text() == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m175_no_match_fail_closed(host):
    window, provider, memory, pool = host
    before = prepare(window, "nao-existe-xyz")
    press_shift_return(window)
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_find_position.text() == "Atual: 0"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


def test_m175_max_96_character_query_inert(host):
    window, provider, memory, pool = host
    before = prepare(window, "A" * 96)
    press_shift_return(window)
    assert window.task_timeline_find_query.text() == "A" * 96
    assert window.task_timeline_find_position.text() == "Atual: 0"
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("category", [0, 1, 2, 3])
def test_m175_reverse_respects_filtered_timeline(host, category):
    window, provider, memory, pool = host
    prepare(window, "Tarefa")
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    QApplication.processEvents()
    before = snapshot(window)
    count = window.task_timeline_find_count.text()
    press_shift_return(window)
    assert window.task_timeline_find_count.text() == count
    assert window.task_timeline_find_query.text() == "Tarefa"
    passive(window, provider, memory, pool, before)


def test_m175_disabled_shortcut_direct_signal_guard(host):
    window, provider, memory, pool = host
    before = prepare(window)
    shortcut = window.task_timeline_find_previous_shortcut
    shortcut.setEnabled(False)
    try:
        shortcut.activated.emit()
        window._find_previous_visible_task_timeline_match_shortcut()
        assert window.task_timeline_view.isHidden()
        assert window.task_timeline_find_position.text() == "Atual: 0"
    finally:
        shortcut.setEnabled(True)
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("name", [
    "task_timeline_find_query", "task_timeline_find_previous",
    "task_timeline_view",
])
def test_m175_disabled_controls_fail_closed(host, name):
    window, provider, memory, pool = host
    before = prepare(window)
    control = getattr(window, name)
    control.setEnabled(False)
    try:
        window.task_timeline_find_previous_shortcut.activated.emit()
        window._find_previous_visible_task_timeline_match_shortcut()
        assert window.task_timeline_view.isHidden()
        assert window.task_timeline_find_position.text() == "Atual: 0"
    finally:
        control.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m175_other_field_does_not_trigger_reverse(host):
    window, provider, memory, pool = host
    before = prepare(window)
    press_shift_return(window, window.input)
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_find_position.text() == "Atual: 0"
    # Composer may handle Shift+Return itself; timeline search must not run.
    assert window.task_timeline_find_query.text() == "falhou"
    assert provider.calls == 0 and not pool.workers
    assert window._memory is memory
    assert snapshot(window)[:8] == before[:8]


def test_m175_two_windows_isolated(host):
    window, provider, memory, pool = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(), other_provider,
        build_default_tool_catalog(),
    )
    try:
        before = prepare(window)
        prepare(other, "cancelada")
        other_before = snapshot(other)
        press_shift_return(window)
        assert window.task_timeline_find_position.text() == "Atual: 3"
        assert other.task_timeline_view.isHidden()
        assert other.task_timeline_find_position.text() == "Atual: 0"
        assert snapshot(other) == other_before
        assert other_provider.calls == 0
        passive(window, provider, memory, pool, before)
    finally:
        other.close()


def test_m175_retain_query_and_count(host):
    window, provider, memory, pool = host
    before = prepare(window)
    old_count = window.task_timeline_find_count.text()
    press_shift_return(window)
    assert window.task_timeline_find_query.text() == "falhou"
    assert window.task_timeline_find_count.text() == old_count
    passive(window, provider, memory, pool, before)


def test_m175_escape_clears_after_shift_return(host):
    window, provider, memory, pool = host
    prepare(window)
    press_shift_return(window)
    widget = window.task_timeline_find_query
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert widget.text() == ""
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    assert window.task_timeline_find_position.text() == "Atual: 0"
    assert provider.calls == 0 and not pool.workers
    assert window._memory is memory


def test_m175_no_provider_memory_worker_effects(host):
    window, provider, memory, pool = host
    before = prepare(window)
    press_shift_return(window)
    window.task_timeline_find_previous_shortcut.activated.emit()
    assert window.task_timeline_find_query.text() == "falhou"
    passive(window, provider, memory, pool, before)
