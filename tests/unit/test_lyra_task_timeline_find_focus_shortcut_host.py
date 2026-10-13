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


def passive(window, provider, memory, pool, state, *, workers=0):
    assert snapshot(window) == state
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert len(pool.workers) == workers


def focus(window, widget):
    window.activateWindow()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert widget.hasFocus()


def shortcut_key(window, source=None):
    widget = window.input if source is None else source
    focus(window, widget)
    QTest.keyClick(
        widget, Qt.Key.Key_F,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def assert_search_focus(window):
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_find_query.hasFocus()


def test_m174_shortcut_identity_context_default_state(host):
    window, provider, memory, pool = host
    shortcut = window.task_timeline_find_focus_shortcut
    assert isinstance(shortcut, QShortcut)
    assert shortcut.key() == QKeySequence("Ctrl+Shift+F")
    assert shortcut.objectName() == "lyra_task_timeline_find_focus_shortcut"
    assert shortcut.parent() is window
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.isEnabled()
    assert window.task_timeline_view.isHidden()
    passive(window, provider, memory, pool, snapshot(window))


def test_m174_real_qt_composer_reveals_hidden_timeline(host):
    window, provider, memory, pool = host
    populate(window)
    assert window.task_timeline_view.isHidden()
    before = snapshot(window)
    shortcut_key(window)
    assert_search_focus(window)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m174_real_qt_from_transcript_search(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    shortcut_key(window, window.transcript_find)
    assert_search_focus(window)
    passive(window, provider, memory, pool, before)


def test_m174_real_qt_from_chat(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    shortcut_key(window, window.chat)
    assert_search_focus(window)
    passive(window, provider, memory, pool, before)


def test_m174_real_qt_from_visible_timeline(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    before = snapshot(window)
    shortcut_key(window, window.task_timeline_view)
    assert_search_focus(window)
    passive(window, provider, memory, pool, before)


def test_m174_repeated_invocations_idempotent(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    shortcut_key(window)
    for _ in range(3):
        window.task_timeline_find_focus_shortcut.activated.emit()
        QApplication.processEvents()
        assert_search_focus(window)
    passive(window, provider, memory, pool, before)


def test_m174_preserves_existing_bounded_query(host):
    window, provider, memory, pool = host
    populate(window)
    query = "A" * 96
    window.task_timeline_find_query.setText(query)
    before = snapshot(window)
    count = window.task_timeline_find_count.text()
    window.input.setText("rascunho existente")
    before = snapshot(window)
    shortcut_key(window)
    assert_search_focus(window)
    assert window.task_timeline_find_query.text() == query
    assert window.task_timeline_find_count.text() == count
    passive(window, provider, memory, pool, before)


def test_m174_preserves_selected_match_and_readouts(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_find_query.setText("falhou")
    window.task_timeline_find_next.click()
    QApplication.processEvents()
    cursor = window.task_timeline_view.textCursor()
    assert cursor.hasSelection()
    selected = (cursor.selectionStart(), cursor.selectionEnd())
    readouts = (
        window.task_timeline_find_count.text(),
        window.task_timeline_find_position.text(),
    )
    before = snapshot(window)
    shortcut_key(window)
    assert_search_focus(window)
    updated = window.task_timeline_view.textCursor()
    assert (updated.selectionStart(), updated.selectionEnd()) == selected
    assert readouts == (
        window.task_timeline_find_count.text(),
        window.task_timeline_find_position.text(),
    )
    passive(window, provider, memory, pool, before)


def test_m174_preserves_scrollbar_percent_and_history(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    bar.setValue(bar.maximum() // 2)
    old_value = bar.value()
    readouts = (
        window.task_timeline_scroll_position.text(),
        window.task_timeline_seek_percent_value.text(),
    )
    before = snapshot(window)
    shortcut_key(window)
    assert_search_focus(window)
    assert bar.value() == old_value
    assert readouts == (
        window.task_timeline_scroll_position.text(),
        window.task_timeline_seek_percent_value.text(),
    )
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("category", [0, 1, 3])
def test_m174_preserves_active_interruption_categories(host, category):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    QApplication.processEvents()
    before = snapshot(window)
    count = window.task_timeline_visible_count.text()
    scope = window.task_timeline_view_scope.text()
    shortcut_key(window)
    assert_search_focus(window)
    assert window.task_timeline_visible_count.text() == count
    assert window.task_timeline_view_scope.text() == scope
    passive(window, provider, memory, pool, before)


def test_m174_disabled_shortcut_fails_closed(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    focus(window, window.input)
    window.task_timeline_find_focus_shortcut.setEnabled(False)
    try:
        window.task_timeline_find_focus_shortcut.activated.emit()
        window._focus_visible_task_timeline_find_shortcut()
        assert window.input.hasFocus()
        assert window.task_timeline_view.isHidden()
    finally:
        window.task_timeline_find_focus_shortcut.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m174_disabled_query_fails_closed(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    focus(window, window.input)
    window.task_timeline_find_query.setEnabled(False)
    try:
        window.task_timeline_find_focus_shortcut.activated.emit()
        window._focus_visible_task_timeline_find_shortcut()
        assert window.input.hasFocus()
        assert window.task_timeline_view.isHidden()
    finally:
        window.task_timeline_find_query.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m174_disabled_toggle_fails_closed(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    focus(window, window.input)
    window.task_timeline_toggle.setEnabled(False)
    try:
        window.task_timeline_find_focus_shortcut.activated.emit()
        window._focus_visible_task_timeline_find_shortcut()
        assert window.input.hasFocus()
        assert window.task_timeline_view.isHidden()
    finally:
        window.task_timeline_toggle.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m174_disabled_view_fails_closed(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    focus(window, window.input)
    window.task_timeline_view.setEnabled(False)
    try:
        window.task_timeline_find_focus_shortcut.activated.emit()
        window._focus_visible_task_timeline_find_shortcut()
        assert window.input.hasFocus()
        assert window.task_timeline_view.isHidden()
    finally:
        window.task_timeline_view.setEnabled(True)
    passive(window, provider, memory, pool, before)


def test_m174_two_real_qt_windows_isolated(host):
    window, provider, memory, pool = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(), other_provider,
        build_default_tool_catalog(),
    )
    try:
        populate(window)
        populate(other)
        other.task_timeline_find_query.setText("não modificar")
        old_query = other.task_timeline_find_query.text()
        assert other.task_timeline_view.isHidden()
        before = snapshot(window)
        shortcut_key(window)
        assert_search_focus(window)
        assert other.task_timeline_view.isHidden()
        assert other.task_timeline_find_query.text() == old_query
        assert provider.calls == 0 and other_provider.calls == 0
        passive(window, provider, memory, pool, before)
    finally:
        other.close()


def test_m174_busy_task_does_not_dispatch(host):
    window, provider, memory, pool = host
    populate(window)
    window._start_tool_task("simulação", ())
    assert len(pool.workers) == 1
    before = snapshot(window)
    window.task_timeline_find_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert len(pool.workers) == 1
    assert provider.calls == 0
    assert window._memory is memory
    assert snapshot(window) == before


def test_m174_no_query_no_navigation_no_side_effects(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    count = window.task_timeline_find_count.text()
    position = window.task_timeline_find_position.text()
    shortcut_key(window)
    assert_search_focus(window)
    assert window.task_timeline_find_query.text() == ""
    assert window.task_timeline_find_count.text() == count
    assert window.task_timeline_find_position.text() == position
    passive(window, provider, memory, pool, before)
