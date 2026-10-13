from __future__ import annotations

import re

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
        raise AssertionError("external continuation forbidden")

    def reply(self, text, *, history=()):
        raise AssertionError("external reply forbidden")


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
    dry = DryPool()
    window._pool = dry
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def fill(window):
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


def state(window):
    timeline = window._task_timeline
    return (
        timeline.snapshot(), timeline.summary(), timeline.interruption_count_label(),
        timeline.interruption_breakdown_label(),
        window.task_timeline_interruptions_only.isChecked(),
        window.task_timeline_interruption_category.currentIndex(),
        window.task_timeline_interruption_category.currentData(), window.input.text(),
        window.transcript_find.text(), window.chat.toPlainText(),
        window.chat_follow.isChecked(),
    )


def passive(window, provider, memory, dry, before):
    assert state(window) == before
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert not dry.workers


def search(window, query, *, keyboard=False):
    window.task_timeline_find_query.setText(query)
    if keyboard:
        window.task_timeline_find_query.returnPressed.emit()
    else:
        window.task_timeline_find_next.click()
    QApplication.processEvents()


def selected(window):
    return window.task_timeline_view.textCursor().selectedText()


def show(window):
    fill(window)
    window.show()
    QApplication.processEvents()




def previous(window, query, *, direct=False):
    window.task_timeline_find_query.setText(query)
    if direct:
        window._find_previous_visible_task_timeline_match()
    else:
        window.task_timeline_find_previous.click()
    QApplication.processEvents()


def move_to_start(window):
    cursor = window.task_timeline_view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    window.task_timeline_view.setTextCursor(cursor)
    QApplication.processEvents()


def test_m169_previous_controls_identity_and_accessibility(host):
    window, provider, memory, dry = host
    button = window.task_timeline_find_previous
    assert isinstance(button, QPushButton)
    assert button.objectName() == "lyra_task_timeline_find_previous"
    assert button.text() == "Ocorrência anterior"
    assert button.accessibleName() and button.toolTip()
    assert window.task_timeline_find_query.maxLength() == 96
    passive(window, provider, memory, dry, state(window))


def test_m169_empty_query_is_noop(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    cursor = window.task_timeline_view.textCursor()
    previous(window, "")
    assert window.task_timeline_view.textCursor() == cursor
    assert not selected(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("needle", ("cancelada", "CANCELADA", "CaNcElAdA"))
def test_m169_previous_case_insensitive(host, needle):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    move_to_start(window)
    previous(window, needle)
    assert selected(window).casefold() == "cancelada"
    passive(window, provider, memory, dry, before)


def test_m169_previous_from_start_wraps_to_last(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    move_to_start(window)
    previous(window, "cancelada")
    last = window.task_timeline_view.textCursor().selectionStart()
    positions = [m.start() for m in re.finditer('cancelada', window.task_timeline_view.toPlainText().lower())]
    assert len(positions) == 3
    assert last == positions[-1]
    passive(window, provider, memory, dry, before)


def test_m169_previous_walks_back_and_wraps(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    positions = [m.start() for m in re.finditer('cancelada', window.task_timeline_view.toPlainText().lower())]
    assert len(positions) == 3
    move_to_start(window)
    for expected in (*reversed(positions), positions[-1]):
        previous(window, "cancelada")
        assert window.task_timeline_view.textCursor().selectionStart() == expected
    passive(window, provider, memory, dry, before)


def test_m169_next_and_previous_are_inverse(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    move_to_start(window)
    search(window, "falhou")
    first = window.task_timeline_view.textCursor().selectionStart()
    search(window, "falhou")
    second = window.task_timeline_view.textCursor().selectionStart()
    assert second > first
    previous(window, "falhou")
    assert window.task_timeline_view.textCursor().selectionStart() == first
    passive(window, provider, memory, dry, before)


def test_m169_absent_match_keeps_selection_and_scrollbar(host):
    window, provider, memory, dry = host
    show(window)
    search(window, "falhou")
    before = state(window)
    cursor = window.task_timeline_view.textCursor()
    scrollbar = window.task_timeline_view.verticalScrollBar().value()
    previous(window, "not-a-task-event-xyz")
    assert window.task_timeline_view.textCursor() == cursor
    assert window.task_timeline_view.verticalScrollBar().value() == scrollbar
    passive(window, provider, memory, dry, before)


def test_m169_absent_match_does_not_show_hidden_timeline(host):
    window, provider, memory, dry = host
    show(window)
    window.task_timeline_view.hide()
    before = state(window)
    previous(window, "never-present-xyz")
    assert window.task_timeline_view.isHidden()
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("disabled", ("query", "previous", "view"))
def test_m169_disabled_controls_fail_closed(host, disabled):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    widget = {"query": window.task_timeline_find_query,
              "previous": window.task_timeline_find_previous,
              "view": window.task_timeline_view}[disabled]
    window.task_timeline_find_query.setText("falhou")
    widget.setEnabled(False)
    cursor = window.task_timeline_view.textCursor()
    window._find_previous_visible_task_timeline_match()
    assert window.task_timeline_view.textCursor() == cursor
    passive(window, provider, memory, dry, before)


def test_m169_previous_only_sees_current_filtered_events(host):
    window, provider, memory, dry = host
    show(window)
    window.task_timeline_interruptions_only.setChecked(True)
    index = window.task_timeline_interruption_category.findData("failed")
    assert index >= 0
    window.task_timeline_interruption_category.setCurrentIndex(index)
    QApplication.processEvents()
    before = state(window)
    previous(window, "cancelada")
    assert not selected(window)
    previous(window, "falhou")
    assert selected(window).casefold() == "falhou"
    passive(window, provider, memory, dry, before)


def test_m169_filter_change_invalidates_old_selection(host):
    window, provider, memory, dry = host
    show(window)
    search(window, "cancelada")
    window.task_timeline_interruptions_only.setChecked(True)
    index = window.task_timeline_interruption_category.findData("failed")
    window.task_timeline_interruption_category.setCurrentIndex(index)
    QApplication.processEvents()
    before = state(window)
    previous(window, "cancelada")
    assert not selected(window)
    passive(window, provider, memory, dry, before)


def test_m169_96_character_query_limit(host):
    window, provider, memory, dry = host
    window.task_timeline_find_query.setText("x" * 300)
    assert len(window.task_timeline_find_query.text()) == 96
    before = state(window)
    window._find_previous_visible_task_timeline_match()
    passive(window, provider, memory, dry, before)


def test_m169_two_windows_isolate_search_and_selection(host):
    left, provider, memory, dry = host
    other_provider = ControlledProvider()
    other_memory = object()
    right = MainWindow(ActionRegistry(), other_memory, other_provider,
                       build_default_tool_catalog())
    other_dry = DryPool()
    right._pool = other_dry
    try:
        show(left)
        show(right)
        left_before, right_before = state(left), state(right)
        previous(left, "falhou")
        assert selected(left).casefold() == "falhou"
        assert not selected(right)
        assert not right.task_timeline_find_query.text()
        passive(left, provider, memory, dry, left_before)
        passive(right, other_provider, other_memory, other_dry, right_before)
    finally:
        right.close()


def test_m169_previous_preserves_draft_memory_and_tasks(host):
    window, provider, memory, dry = host
    show(window)
    window.input.setText("rascunho protegido")
    before = state(window)
    for needle in ("falhou", "cancelada", "iniciada", "ausente"):
        previous(window, needle)
    assert window.input.text() == "rascunho protegido"
    passive(window, provider, memory, dry, before)
