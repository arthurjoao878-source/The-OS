from __future__ import annotations

import pytest
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
    window = MainWindow(ActionRegistry(), memory, provider, build_default_tool_catalog())
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


def set_query(window, query):
    window.task_timeline_find_query.setText(query)
    QApplication.processEvents()


def count_label(window):
    return window.task_timeline_find_count.text()


def expected_count(window, term):
    return window.task_timeline_view.toPlainText().casefold().count(term.casefold())


def test_m171_count_label_identity_and_initial_zero(host):
    window, provider, memory, pool = host
    label = window.task_timeline_find_count
    assert isinstance(label, QLabel)
    assert label.objectName() == "lyra_task_timeline_find_count"
    assert label.accessibleName() and label.toolTip()
    assert count_label(window) == "Ocorrências: 0"
    assert window.task_timeline_find_query.maxLength() == 96
    passive(window, provider, memory, pool, snapshot(window))


def test_m171_empty_query_stays_zero_after_populate(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    assert count_label(window) == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


@pytest.mark.parametrize("term", ("falhou", "FALHOU", "cancelada"))
def test_m171_live_case_insensitive_count(host, term):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, term)
    assert expected_count(window, term) > 0
    assert count_label(window) == f"Ocorrências: {expected_count(window, term)}"
    passive(window, provider, memory, pool, before)


def test_m171_no_match_zero(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "nunca-aparecera-123")
    assert count_label(window) == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


def test_m171_query_edit_recalculates_without_navigation(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    initial_cursor = window.task_timeline_view.textCursor()
    set_query(window, "falhou")
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'falhou')}"
    set_query(window, "cancelada")
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'cancelada')}"
    assert window.task_timeline_view.textCursor() == initial_cursor
    passive(window, provider, memory, pool, before)


def test_m171_clear_button_zero_and_no_event_mutation(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    assert count_label(window) != "Ocorrências: 0"
    window.task_timeline_find_next.click()
    QApplication.processEvents()
    cursor = window.task_timeline_view.textCursor()
    assert cursor.hasSelection()
    window.task_timeline_find_clear.click()
    QApplication.processEvents()
    assert not window.task_timeline_view.textCursor().hasSelection()
    assert count_label(window) == "Ocorrências: 0"
    assert window.task_timeline_find_query.text() == ""
    passive(window, provider, memory, pool, before)


def test_m171_next_previous_selection_does_not_change_count(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "falhou")
    original = count_label(window)
    window.task_timeline_find_next.click()
    window.task_timeline_find_previous.click()
    QApplication.processEvents()
    assert count_label(window) == original
    passive(window, provider, memory, pool, before)


def test_m171_filter_switch_recounts_with_current_query(host):
    window, provider, memory, pool = host
    populate(window)
    set_query(window, "falhou")
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    before = snapshot(window)
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'falhou')}"
    window.task_timeline_interruptions_only.setChecked(False)
    QApplication.processEvents()
    after = snapshot(window)
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'falhou')}"
    passive(window, provider, memory, pool, after)
    assert before[0] == after[0]


def test_m171_repopulate_recounts_without_changing_query(host):
    window, provider, memory, pool = host
    populate(window)
    set_query(window, "cancelada")
    before = snapshot(window)
    window._refresh_task_timeline()
    QApplication.processEvents()
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'cancelada')}"
    assert window.task_timeline_find_query.text() == "cancelada"
    passive(window, provider, memory, pool, before)


def test_m171_query_max_length_remains_96(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    set_query(window, "Z" * 120)
    assert len(window.task_timeline_find_query.text()) == 96
    assert count_label(window) == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


def test_m171_count_cap_exact_256(host):
    window, provider, memory, pool = host
    window.task_timeline_view.setPlainText("xyz " * 256)
    set_query(window, "xyz")
    assert count_label(window) == "Ocorrências: 256"
    assert not window.task_timeline_view.textCursor().hasSelection()
    assert provider.calls == 0 and not pool.workers and window._memory is memory


def test_m171_count_cap_over_256(host):
    window, provider, memory, pool = host
    window.task_timeline_view.setPlainText("xyz " * 300)
    set_query(window, "xyz")
    assert count_label(window) == "Ocorrências: 256+"
    assert not window.task_timeline_view.textCursor().hasSelection()
    assert provider.calls == 0 and not pool.workers and window._memory is memory


def test_m171_direct_document_change_updates_count(host):
    window, provider, memory, pool = host
    set_query(window, "evento")
    assert count_label(window) == "Ocorrências: 0"
    window.task_timeline_view.setPlainText("evento\noutro evento\nfim")
    QApplication.processEvents()
    assert count_label(window) == "Ocorrências: 2"
    assert window.task_timeline_find_query.text() == "evento"
    assert provider.calls == 0 and not pool.workers and window._memory is memory


def test_m171_hidden_view_not_revealed_on_recount(host):
    window, provider, memory, pool = host
    populate(window)
    window.task_timeline_view.hide()
    assert window.task_timeline_view.isHidden()
    set_query(window, "falhou")
    assert window.task_timeline_view.isHidden()
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'falhou')}"
    assert provider.calls == 0 and not pool.workers and window._memory is memory


def test_m171_two_windows_isolated(host):
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
        state_first, state_second = snapshot(first), snapshot(second)
        set_query(first, "falhou")
        set_query(second, "cancelada")
        assert count_label(first) == f"Ocorrências: {expected_count(first, 'falhou')}"
        assert count_label(second) == f"Ocorrências: {expected_count(second, 'cancelada')}"
        first.task_timeline_find_clear.click()
        assert count_label(first) == "Ocorrências: 0"
        assert count_label(second) != "Ocorrências: 0"
        passive(first, provider, memory, pool, state_first)
        passive(second, second_provider, second_memory, second_pool, state_second)
    finally:
        second.close()


def test_m171_disabled_view_still_read_only_count(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    window.task_timeline_view.setEnabled(False)
    set_query(window, "falhou")
    assert count_label(window) == f"Ocorrências: {expected_count(window, 'falhou')}"
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0 and not pool.workers and window._memory is memory
    window.task_timeline_view.setEnabled(True)
    passive(window, provider, memory, pool, before)
