from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QTextCursor
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
        return AIReply(text="controlled", provider_id="controlled")

    def continue_after_tools(self, turn, results):
        raise AssertionError("continuation forbidden")

    def reply(self, text, *, history=()):
        raise AssertionError("reply forbidden")


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
        text, terminal = (
            ("Tarefa: iniciada · 0/4 etapas", False),
            ("Tarefa: cancelamento solicitado · aguardando confirmação", False),
            ("Tarefa: cancelada · 0/4 etapas", True),
            ("Tarefa: falhou · 1/4 etapas · sistema", True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=text, terminal=terminal)
        )
    window._refresh_task_timeline()
    window.show()
    QApplication.processEvents()


def snapshot(window):
    timeline = window._task_timeline
    return (
        timeline.snapshot(),
        timeline.summary(),
        timeline.interruption_count_label(),
        timeline.interruption_breakdown_label(),
        window.task_timeline_interruptions_only.isChecked(),
        window.task_timeline_interruption_category.currentIndex(),
        window.task_timeline_interruption_category.currentData(),
        window.task_timeline_view.toPlainText(),
        window.input.text(),
        window.transcript_find.text(),
        window.chat.toPlainText(),
        window.chat_follow.isChecked(),
    )


def passive(window, provider, memory, pool, state):
    assert snapshot(window) == state
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert pool.workers == []


def set_query(window, value):
    window.task_timeline_find_query.setText(value)
    QApplication.processEvents()


def ordinal(window):
    return window.task_timeline_find_position.text()


def select_from_start(window):
    cursor = QTextCursor(window.task_timeline_view.document())
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    window.task_timeline_view.setTextCursor(cursor)
    QApplication.processEvents()


def next_match(window):
    window.task_timeline_find_next.click()
    QApplication.processEvents()


def previous_match(window):
    window.task_timeline_find_previous.click()
    QApplication.processEvents()




def focus_widget(window, widget):
    window.show()
    window.activateWindow()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert widget.hasFocus()


def escape(widget):
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    QApplication.processEvents()


def test_m173_shortcut_identity_and_scope(host):
    window, provider, memory, pool = host
    shortcut = window.task_timeline_find_escape_shortcut
    assert shortcut.objectName() == "lyra_task_timeline_find_escape_shortcut"
    assert shortcut.parent() is window.task_timeline_find_query
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    assert shortcut.key() == QKeySequence("Escape")
    assert shortcut.isEnabled()
    passive(window, provider, memory, pool, snapshot(window))


def test_m173_escape_clears_typed_query(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m173_escape_after_next_clears_selection(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    next_match(window)
    assert ordinal(window) != "Atual: 0"
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert not window.task_timeline_view.textCursor().hasSelection()
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m173_escape_after_previous_clears_selection(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "cancelada")
    previous_match(window)
    assert ordinal(window) != "Atual: 0"
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert not window.task_timeline_view.textCursor().hasSelection()
    passive(window, provider, memory, pool, before)


def test_m173_escape_on_empty_query_is_noop(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    focus_widget(window, window.task_timeline_find_query)
    cursor_before = window.task_timeline_view.textCursor()
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    assert window.task_timeline_view.textCursor() == cursor_before
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("query", ["FALHOU", "falhou"])
def test_m173_escape_case_independent(host, query):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, query)
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m173_escape_in_composer_does_not_clear_timeline(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    focus_widget(window, window.input)
    escape(window.input)
    assert window.task_timeline_find_query.text() == "falhou"
    passive(window, provider, memory, pool, before)


def test_m173_escape_in_transcript_search_does_not_clear_timeline(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    focus_widget(window, window.transcript_find)
    escape(window.transcript_find)
    assert window.task_timeline_find_query.text() == "falhou"
    passive(window, provider, memory, pool, before)


def test_m173_escape_in_timeline_view_does_not_clear_query(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    assert window.task_timeline_view.isHidden()
    window.task_timeline_view.show()
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    focus_widget(window, window.task_timeline_view)
    escape(window.task_timeline_view)
    assert window.task_timeline_find_query.text() == "falhou"
    passive(window, provider, memory, pool, before)


def test_m173_direct_shortcut_signal_respects_disabled_query(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    window.task_timeline_find_query.setEnabled(False)
    window.task_timeline_find_escape_shortcut.activated.emit()
    assert window.task_timeline_find_query.text() == "falhou"
    window.task_timeline_find_query.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m173_direct_shortcut_signal_respects_disabled_clear(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    window.task_timeline_find_clear.setEnabled(False)
    window.task_timeline_find_escape_shortcut.activated.emit()
    assert window.task_timeline_find_query.text() == "falhou"
    window.task_timeline_find_clear.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m173_direct_shortcut_signal_respects_disabled_view(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    window.task_timeline_view.setEnabled(False)
    window.task_timeline_find_escape_shortcut.activated.emit()
    assert window.task_timeline_find_query.text() == "falhou"
    window.task_timeline_view.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m173_escape_preserves_filtered_history(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    before = snapshot(window)
    set_query(window, "falhou")
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m173_escape_after_no_match_restores_zero(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "NOT_A_REAL_MATCH")
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m173_escape_preserves_viewport_position(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    scroll = window.task_timeline_view.verticalScrollBar()
    set_query(window, "falhou")
    focus_widget(window, window.task_timeline_find_query)
    old = scroll.value()
    escape(window.task_timeline_find_query)
    assert scroll.value() == old
    passive(window, provider, memory, pool, before)


def test_m173_escape_does_not_cross_windows(host):
    first, provider, memory, pool = host
    populate(first)
    state = snapshot(first)
    second_provider = ControlledProvider()
    second_memory = object()
    second = MainWindow(
        ActionRegistry(), second_memory, second_provider,
        build_default_tool_catalog(),
    )
    second_pool = DryPool()
    second._pool = second_pool
    try:
        populate(second)
        second_state = snapshot(second)
        set_query(first, "falhou")
        set_query(second, "cancelada")
        focus_widget(first, first.task_timeline_find_query)
        escape(first.task_timeline_find_query)
        assert first.task_timeline_find_query.text() == ""
        assert second.task_timeline_find_query.text() == "cancelada"
        passive(first, provider, memory, pool, state)
        passive(second, second_provider, second_memory, second_pool, second_state)
    finally:
        second.close()


def test_m173_escape_max_query_bound_and_no_dispatch(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "x" * 400)
    assert len(window.task_timeline_find_query.text()) == 96
    focus_widget(window, window.task_timeline_find_query)
    escape(window.task_timeline_find_query)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)
