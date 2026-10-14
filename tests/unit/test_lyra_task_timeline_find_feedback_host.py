from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
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



def test_m176_default_identity_accessibility(host):
    window, provider, memory, pool = host
    label = window.task_timeline_find_feedback
    assert label.objectName() == "lyra_task_timeline_find_feedback"
    assert label.accessibleName() == "Estado da busca no histórico de tarefas visível"
    assert label.text() == "Busca: inativa"
    passive(window, provider, memory, pool, snapshot(window))


def test_m176_empty_query_remains_inactive(host):
    window, provider, memory, pool = host
    before = prepare(window, "")
    assert window.task_timeline_find_feedback.text() == "Busca: inativa"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


def test_m176_unmatched_query_distinct_from_empty(host):
    window, provider, memory, pool = host
    before = prepare(window, "naoencontra987")
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    passive(window, provider, memory, pool, before)


def test_m176_matched_query_indicates_occurrences(host):
    window, provider, memory, pool = host
    before = prepare(window, "falhou")
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    assert window.task_timeline_find_count.text() == "Ocorrências: 3"
    assert window.task_timeline_find_position.text() == "Atual: 0"
    passive(window, provider, memory, pool, before)


def test_m176_case_insensitive_match(host):
    window, provider, memory, pool = host
    before = prepare(window, "FALHOU")
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    passive(window, provider, memory, pool, before)


def test_m176_empty_document_query_no_results(host):
    window, provider, memory, pool = host
    window.task_timeline_find_query.setText("nuncaexiste178")
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    passive(window, provider, memory, pool, snapshot(window))


def test_m176_transition_match_to_no_match_to_inactive(host):
    window, provider, memory, pool = host
    populate(window)
    before = snapshot(window)
    query = window.task_timeline_find_query
    query.setText("falhou")
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    query.setText("naoencontra987")
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    query.clear()
    assert window.task_timeline_find_feedback.text() == "Busca: inativa"
    passive(window, provider, memory, pool, before)


def test_m176_enter_next_preserves_status(host):
    window, provider, memory, pool = host
    before = prepare(window)
    window.task_timeline_find_next.click()
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    assert window.task_timeline_find_position.text() == "Atual: 1"
    passive(window, provider, memory, pool, before)


def test_m176_previous_button_preserves_status(host):
    window, provider, memory, pool = host
    before = prepare(window)
    window.task_timeline_find_previous.click()
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    assert window.task_timeline_find_position.text() == "Atual: 3"
    passive(window, provider, memory, pool, before)


def test_m176_shift_enter_previous_preserves_status(host):
    window, provider, memory, pool = host
    before = prepare(window)
    press_shift_return(window)
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    passive(window, provider, memory, pool, before)


def test_m176_escape_clear_returns_inactive(host):
    window, provider, memory, pool = host
    prepare(window)
    press_shift_return(window)
    query = window.task_timeline_find_query
    QTest.keyClick(query, Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert query.text() == ""
    assert window.task_timeline_find_feedback.text() == "Busca: inativa"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    assert provider.calls == 0 and not pool.workers
    assert window._memory is memory


def test_m176_clear_button_returns_inactive(host):
    window, provider, memory, pool = host
    prepare(window)
    window.task_timeline_find_clear.click()
    assert window.task_timeline_find_feedback.text() == "Busca: inativa"
    assert provider.calls == 0 and not pool.workers and window._memory is memory


def test_m176_filter_changes_visible_scope(host):
    window, provider, memory, pool = host
    before = prepare(window, "falhou")
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    QApplication.processEvents()
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    assert window.task_timeline_find_count.text() == "Ocorrências: 0"
    assert window._task_timeline.snapshot() == before[0]
    assert provider.calls == 0 and not pool.workers
    assert window._memory is memory


def test_m176_document_update_recomputes_status(host):
    window, provider, memory, pool = host
    before = prepare(window, "naoencontra987")
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    window.task_timeline_view.setPlainText("naoencontra987")
    QApplication.processEvents()
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    assert window._task_timeline.snapshot() == before[0]
    assert provider.calls == 0 and not pool.workers
    assert window._memory is memory


def test_m176_query_96_character_bound_no_match(host):
    window, provider, memory, pool = host
    before = prepare(window, "z" * 96)
    assert len(window.task_timeline_find_query.text()) == 96
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    passive(window, provider, memory, pool, before)


def test_m176_query_limit_truncates_input(host):
    window, provider, memory, pool = host
    before = prepare(window, "z" * 120)
    assert len(window.task_timeline_find_query.text()) == 96
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    passive(window, provider, memory, pool, before)


def test_m176_two_windows_independent(host):
    window, provider, memory, pool = host
    other_provider = ControlledProvider()
    other = MainWindow(ActionRegistry(), object(), other_provider, build_default_tool_catalog())
    try:
        before = prepare(window, "falhou")
        prepare(other, "semresultados987")
        assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
        assert other.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
        other.task_timeline_find_query.clear()
        assert other.task_timeline_find_feedback.text() == "Busca: inativa"
        assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
        assert other_provider.calls == 0
        passive(window, provider, memory, pool, before)
    finally:
        other.close()


def test_m176_status_no_second_search_side_effect(host):
    window, provider, memory, pool = host
    before = prepare(window)
    for _ in range(3):
        window._refresh_visible_task_timeline_find_count()
    assert window.task_timeline_find_feedback.text() == "Busca: com ocorrências"
    assert window.task_timeline_find_count.text() == "Ocorrências: 3"
    passive(window, provider, memory, pool, before)


def test_m176_draft_and_transcript_unchanged(host):
    window, provider, memory, pool = host
    window.input.setText("Rascunho do usuário")
    window.transcript_find.setText("consulta")
    before = prepare(window, "falhou")
    window.task_timeline_find_query.setText("naoencontra987")
    assert window.task_timeline_find_feedback.text() == "Busca: sem ocorrências"
    assert snapshot(window)[:8] == before[:8]
    assert window.input.text() == before[8]
    assert window.transcript_find.text() == before[9]
    assert provider.calls == 0 and not pool.workers and window._memory is memory
