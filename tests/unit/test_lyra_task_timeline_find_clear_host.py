from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QPushButton

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
    window = MainWindow(ActionRegistry(), memory, provider, build_default_tool_catalog())
    pool = DryPool()
    window._pool = pool
    try:
        yield window, provider, memory, pool
    finally:
        window.close()


def populate(window):
    for i in range(12):
        text, terminal = (
            ("Tarefa: iniciada · 0/4 etapas", False),
            ("Tarefa: cancelamento solicitado · aguardando confirmação", False),
            ("Tarefa: cancelada · 0/4 etapas", True),
            ("Tarefa: falhou · 1/4 etapas · sistema", True),
        )[i % 4]
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


def find(window, term, previous=False):
    window.task_timeline_find_query.setText(term)
    if previous:
        window.task_timeline_find_previous.click()
    else:
        window.task_timeline_find_next.click()
    QApplication.processEvents()


def clear(window, direct=False):
    if direct:
        window._clear_visible_task_timeline_find()
    else:
        window.task_timeline_find_clear.click()
    QApplication.processEvents()


def selection(window):
    return window.task_timeline_view.textCursor().selectedText()


def test_m170_clear_button_identity(host):
    window, provider, memory, pool = host
    button = window.task_timeline_find_clear
    assert isinstance(button, QPushButton)
    assert button.objectName() == "lyra_task_timeline_find_clear"
    assert button.text() == "Limpar busca"
    assert button.accessibleName() and button.toolTip()
    assert window.task_timeline_find_query.maxLength() == 96
    passive(window, provider, memory, pool, snapshot(window))


def test_m170_empty_query_noop(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    cursor = window.task_timeline_view.textCursor()
    clear(window)
    assert window.task_timeline_view.textCursor() == cursor
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("term", ("falhou", "CANCELADA", "iniciada"))
def test_m170_clear_after_next_find(host, term):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    find(window, term)
    assert selection(window).casefold() == term.casefold()
    position = window.task_timeline_view.textCursor().position()
    clear(window)
    assert window.task_timeline_find_query.text() == ""
    assert not window.task_timeline_view.textCursor().hasSelection()
    assert window.task_timeline_view.textCursor().position() == position
    passive(window, provider, memory, pool, before)


def test_m170_clear_after_previous_find(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    find(window, "cancelada", previous=True)
    assert selection(window).casefold() == "cancelada"
    clear(window)
    assert window.task_timeline_find_query.text() == ""
    assert not window.task_timeline_view.textCursor().hasSelection()
    passive(window, provider, memory, pool, before)


def test_m170_clear_without_match(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    find(window, "nothing-matches-this-event")
    assert not selection(window)
    clear(window)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m170_clear_idempotent(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    find(window, "falhou")
    clear(window)
    cursor = window.task_timeline_view.textCursor()
    clear(window)
    assert window.task_timeline_view.textCursor() == cursor
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("disabled", ("query", "clear", "view"))
def test_m170_disabled_controls_fail_closed(host, disabled):
    window, provider, memory, pool = host
    populate(window)
    find(window, "falhou")
    before = snapshot(window)
    cursor = window.task_timeline_view.textCursor()
    control = {
        "query": window.task_timeline_find_query,
        "clear": window.task_timeline_find_clear,
        "view": window.task_timeline_view,
    }[disabled]
    control.setEnabled(False)
    clear(window, direct=True)
    assert window.task_timeline_find_query.text() == "falhou"
    assert window.task_timeline_view.textCursor() == cursor
    passive(window, provider, memory, pool, before)
    control.setEnabled(True)


def test_m170_clear_leaves_filter_in_place(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    before = snapshot(window)
    find(window, "cancelada")
    assert selection(window).casefold() == "cancelada"
    clear(window)
    assert window.task_timeline_interruptions_only.isChecked()
    passive(window, provider, memory, pool, before)


def test_m170_clear_retains_scroll_position(host):
    window, provider, memory, pool = host
    populate(window)
    find(window, "falhou")
    bar = window.task_timeline_view.verticalScrollBar()
    at = bar.value()
    before = snapshot(window)
    clear(window)
    assert bar.value() == at
    passive(window, provider, memory, pool, before)


def test_m170_two_windows_are_isolated(host):
    first, provider, memory, pool = host
    populate(first)
    second_provider = ControlledProvider()
    second_memory = object()
    second = MainWindow(
        ActionRegistry(), second_memory, second_provider, build_default_tool_catalog()
    )
    second_pool = DryPool()
    second._pool = second_pool
    try:
        populate(second)
        find(first, "falhou")
        find(second, "cancelada")
        before_first = snapshot(first)
        before_second = snapshot(second)
        clear(first)
        assert first.task_timeline_find_query.text() == ""
        assert second.task_timeline_find_query.text() == "cancelada"
        assert selection(second).casefold() == "cancelada"
        passive(first, provider, memory, pool, before_first)
        passive(second, second_provider, second_memory, second_pool, before_second)
    finally:
        second.close()


def test_m170_next_and_previous_continue_to_work_after_clear(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    find(window, "cancelada")
    clear(window)
    find(window, "falhou", previous=True)
    assert selection(window).casefold() == "falhou"
    clear(window)
    find(window, "iniciada")
    assert selection(window).casefold() == "iniciada"
    passive(window, provider, memory, pool, before)


def test_m170_query_length_still_bounded(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    window.task_timeline_find_query.setText("x" * 150)
    assert len(window.task_timeline_find_query.text()) == 96
    clear(window)
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m170_empty_query_preserves_other_selection(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    cursor = window.task_timeline_view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor, 4)
    window.task_timeline_view.setTextCursor(cursor)
    assert cursor.hasSelection()
    clear(window)
    assert window.task_timeline_view.textCursor() == cursor
    passive(window, provider, memory, pool, before)


def test_m170_clear_when_timeline_hidden(host):
    window, provider, memory, pool = host
    populate(window)
    find(window, "falhou")
    window.task_timeline_view.hide()
    before = snapshot(window)
    clear(window)
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_find_query.text() == ""
    assert not window.task_timeline_view.textCursor().hasSelection()
    passive(window, provider, memory, pool, before)
