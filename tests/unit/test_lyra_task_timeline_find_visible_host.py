from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QPushButton

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


def test_m168_find_controls_identity_accessibility_and_bounds(host):
    window, provider, memory, dry = host
    query = window.task_timeline_find_query
    button = window.task_timeline_find_next
    assert isinstance(query, QLineEdit)
    assert isinstance(button, QPushButton)
    assert query.objectName() == "lyra_task_timeline_find_query"
    assert button.objectName() == "lyra_task_timeline_find_next"
    assert query.maxLength() == 96
    assert query.accessibleName() and query.toolTip() and button.toolTip()
    assert not query.text() and window.task_timeline_view.isReadOnly()
    passive(window, provider, memory, dry, state(window))


def test_m168_empty_query_is_noop(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    hidden = window.task_timeline_view.isHidden()
    search(window, "")
    assert window.task_timeline_view.isHidden() == hidden
    assert not selected(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("needle", ("falhou", "FALHOU", "FaLhOu"))
def test_m168_case_insensitive_find(host, needle):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    search(window, needle)
    assert selected(window).casefold() == "falhou"
    assert not window.task_timeline_view.isHidden()
    passive(window, provider, memory, dry, before)


def test_m168_find_next_advances_and_wraps(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    query = "cancelada"
    search(window, query)
    first = window.task_timeline_view.textCursor().selectionStart()
    search(window, query)
    second = window.task_timeline_view.textCursor().selectionStart()
    assert second > first
    search(window, query)
    third = window.task_timeline_view.textCursor().selectionStart()
    assert third > second
    search(window, query)
    assert window.task_timeline_view.textCursor().selectionStart() == first
    passive(window, provider, memory, dry, before)


def test_m168_return_pressed_matches_button(host):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    window.task_timeline_find_query.setText("iniciada")
    window.task_timeline_find_query.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.task_timeline_find_query, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert selected(window).casefold() == "iniciada"
    passive(window, provider, memory, dry, before)


def test_m168_missing_match_preserves_selection_and_position(host):
    window, provider, memory, dry = host
    show(window)
    search(window, "falhou")
    before = state(window)
    cursor = window.task_timeline_view.textCursor()
    scrollbar = window.task_timeline_view.verticalScrollBar().value()
    search(window, "not-a-timeline-event-xyz")
    assert window.task_timeline_view.textCursor().selectionStart() == cursor.selectionStart()
    assert selected(window).casefold() == "falhou"
    assert window.task_timeline_view.verticalScrollBar().value() == scrollbar
    passive(window, provider, memory, dry, before)


def test_m168_no_match_does_not_reveal_hidden_panel(host):
    window, provider, memory, dry = host
    show(window)
    window.task_timeline_view.hide()
    before = state(window)
    search(window, "never-present-xyz")
    assert window.task_timeline_view.isHidden()
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("disabled", ("query", "button", "view"))
def test_m168_disabled_controls_fail_closed(host, disabled):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    widget = {"query": window.task_timeline_find_query,
              "button": window.task_timeline_find_next,
              "view": window.task_timeline_view}[disabled]
    window.task_timeline_find_query.setText("falhou")
    widget.setEnabled(False)
    window._find_next_visible_task_timeline_match()
    window.task_timeline_find_query.returnPressed.emit()
    assert not selected(window)
    passive(window, provider, memory, dry, before)


def test_m168_finds_within_current_failure_filter_only(host):
    window, provider, memory, dry = host
    show(window)
    window.task_timeline_interruptions_only.setChecked(True)
    index = window.task_timeline_interruption_category.findData("failed")
    assert index >= 0
    window.task_timeline_interruption_category.setCurrentIndex(index)
    QApplication.processEvents()
    before = state(window)
    assert "falhou" in window.task_timeline_view.toPlainText().casefold()
    search(window, "cancelada")
    assert not selected(window)
    search(window, "falhou")
    assert selected(window).casefold() == "falhou"
    passive(window, provider, memory, dry, before)


def test_m168_find_follows_filter_changes(host):
    window, provider, memory, dry = host
    show(window)
    search(window, "cancelada")
    window.task_timeline_interruptions_only.setChecked(True)
    index = window.task_timeline_interruption_category.findData("failed")
    window.task_timeline_interruption_category.setCurrentIndex(index)
    QApplication.processEvents()
    before = state(window)
    search(window, "cancelada")
    assert not selected(window)
    passive(window, provider, memory, dry, before)


def test_m168_length_bound_is_enforced(host):
    window, provider, memory, dry = host
    window.task_timeline_find_query.setText("z" * 150)
    assert len(window.task_timeline_find_query.text()) == 96
    before = state(window)
    window.task_timeline_find_next.click()
    passive(window, provider, memory, dry, before)


def test_m168_two_window_isolation(host):
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
        search(left, "cancelada")
        assert selected(left).casefold() == "cancelada"
        assert not selected(right)
        assert not right.task_timeline_find_query.text()
        passive(left, provider, memory, dry, left_before)
        passive(right, other_provider, other_memory, other_dry, right_before)
    finally:
        right.close()


def test_m168_denied_reset_keeps_query_and_events(host, monkeypatch):
    window, provider, memory, dry = host
    show(window)
    before = state(window)
    search(window, "falhou")
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    QApplication.processEvents()
    assert window.task_timeline_find_query.text() == "falhou"
    passive(window, provider, memory, dry, before)


def test_m168_no_provider_memory_or_worker_calls_during_find(host):
    window, provider, memory, dry = host
    show(window)
    window.input.setText("rascunho importante")
    before = state(window)
    for word in ("iniciada", "falhou", "cancelada", "ausente"):
        search(window, word)
    assert window.input.text() == "rascunho importante"
    passive(window, provider, memory, dry, before)


def test_m168_find_does_not_modify_percent_slider_model(host):
    window, provider, memory, dry = host
    show(window)
    window.task_timeline_seek_percent.setValue(50)
    QApplication.processEvents()
    before = state(window)
    search(window, "iniciada")
    assert window.task_timeline_seek_percent_value.text().endswith("%")
    assert 0 <= window.task_timeline_seek_percent.value() <= 100
    passive(window, provider, memory, dry, before)
