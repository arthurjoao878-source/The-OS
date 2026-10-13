from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

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


def test_m172_indicator_identity_and_initial_zero(host):
    window, provider, memory, pool = host
    label = window.task_timeline_find_position
    assert isinstance(label, QLabel)
    assert label.objectName() == "lyra_task_timeline_find_position"
    assert label.accessibleName() and label.toolTip()
    assert ordinal(window) == "Atual: 0"
    assert window.task_timeline_find_query.maxLength() == 96
    passive(window, provider, memory, pool, snapshot(window))


def test_m172_query_without_selection_remains_zero(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "falhou")
    assert window.task_timeline_find_count.text() != "Ocorrências: 0"
    assert ordinal(window) == "Atual: 0"
    assert not window.task_timeline_view.textCursor().hasSelection()
    passive(window, provider, memory, pool, before)


def test_m172_next_moves_from_first_to_second(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "cancelada")
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    next_match(window)
    assert ordinal(window) == "Atual: 2"
    passive(window, provider, memory, pool, before)


def test_m172_next_wraps_to_first(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "falhou")
    for position in (1, 2, 3, 1):
        next_match(window)
        assert ordinal(window) == f"Atual: {position}"
    passive(window, provider, memory, pool, before)


def test_m172_previous_wraps_to_last(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "cancelada")
    previous_match(window)
    assert ordinal(window) == "Atual: 3"
    previous_match(window)
    assert ordinal(window) == "Atual: 2"
    passive(window, provider, memory, pool, before)


def test_m172_previous_next_inverse(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "falhou")
    next_match(window)
    next_match(window)
    assert ordinal(window) == "Atual: 2"
    previous_match(window)
    assert ordinal(window) == "Atual: 1"
    next_match(window)
    assert ordinal(window) == "Atual: 2"
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("query", ("FALHOU", "falhou"))
def test_m172_case_insensitive_selection(host, query):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, query)
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m172_clear_resets_position_without_mutation(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "falhou")
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    window.task_timeline_find_clear.click()
    QApplication.processEvents()
    assert ordinal(window) == "Atual: 0"
    assert window.task_timeline_find_query.text() == ""
    assert not window.task_timeline_view.textCursor().hasSelection()
    passive(window, provider, memory, pool, before)


def test_m172_query_changes_without_auto_navigate(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    select_from_start(window)
    set_query(window, "falhou")
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    set_query(window, "cancelada")
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m172_no_match_zero_without_selection(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "nao-existe-xyz")
    next_match(window)
    previous_match(window)
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m172_filter_refresh_clears_stale_selection(host):
    window, provider, memory, pool = host
    populate(window)
    select_from_start(window)
    set_query(window, "falhou")
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    assert ordinal(window) == "Atual: 0"
    before = snapshot(window)
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m172_document_refresh_resets_stale_selection(host):
    window, provider, memory, pool = host
    populate(window)
    select_from_start(window)
    set_query(window, "falhou")
    next_match(window)
    assert ordinal(window) == "Atual: 1"
    window.task_timeline_view.setPlainText("apenas outra coisa")
    QApplication.processEvents()
    assert ordinal(window) == "Atual: 0"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    assert provider.calls == 0 and pool.workers == [] and window._memory is memory


def test_m172_query_max_length_stays_bounded(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "Z" * 120)
    assert len(window.task_timeline_find_query.text()) == 96
    assert ordinal(window) == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m172_manual_unrelated_selection_is_not_a_match(host):
    window, provider, memory, pool = host
    window.task_timeline_view.setPlainText("foo bar foo")
    set_query(window, "foo")
    cursor = window.task_timeline_view.textCursor()
    cursor.setPosition(4)
    cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
    window.task_timeline_view.setTextCursor(cursor)
    QApplication.processEvents()
    assert cursor.selectedText() == "bar"
    assert ordinal(window) == "Atual: 0"
    assert provider.calls == 0 and pool.workers == [] and window._memory is memory


@pytest.mark.parametrize("size,number", ((256, "256"), (257, "256+")))
def test_m172_bounded_selection_ordinal(host, size, number):
    window, provider, memory, pool = host
    window.task_timeline_view.setPlainText("foo " * size)
    set_query(window, "foo")
    document = window.task_timeline_view.document()
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    found = document.find("foo", cursor, QTextDocument.FindFlag.FindBackward)
    assert not found.isNull()
    window.task_timeline_view.setTextCursor(found)
    QApplication.processEvents()
    assert ordinal(window) == f"Atual: {number}"
    assert provider.calls == 0 and pool.workers == [] and window._memory is memory


def test_m172_two_windows_are_isolated(host):
    window, provider, memory, pool = host
    app = QApplication.instance() or QApplication([])
    _ = app
    second_provider = ControlledProvider()
    second_memory = object()
    second = MainWindow(
        ActionRegistry(), second_memory, second_provider, build_default_tool_catalog()
    )
    second_pool = DryPool()
    second._pool = second_pool
    try:
        populate(window)
        populate(second)
        original = snapshot(window)
        original_second = snapshot(second)
        select_from_start(window)
        select_from_start(second)
        set_query(window, "falhou")
        set_query(second, "cancelada")
        next_match(window)
        next_match(second)
        next_match(second)
        assert ordinal(window) == "Atual: 1"
        assert ordinal(second) == "Atual: 2"
        window.task_timeline_find_clear.click()
        QApplication.processEvents()
        assert ordinal(window) == "Atual: 0"
        assert ordinal(second) == "Atual: 2"
        passive(window, provider, memory, pool, original)
        passive(second, second_provider, second_memory, second_pool, original_second)
    finally:
        second.close()
