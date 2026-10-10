from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import LyraRunState
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import (
    TASK_TIMELINE_EMPTY,
    TASK_TIMELINE_LIMIT,
    TASK_TIMELINE_MAX_ENTRY_CHARS,
    TaskTimeline,
)
from theos.shell.assistant.workflow_progress import (
    HostWorkflowProgressView,
    present_run_state,
)


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="ok", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("unexpected continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected provider reply")


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
    try:
        yield window, provider, memory
    finally:
        window.close()


def started() -> LyraRunState:
    return LyraRunState.start("Solicitação confidencial que não deve aparecer.", max_steps=4)


def running() -> LyraRunState:
    return started().begin_action(
        ActionRequest(action="system_status", arguments={"secret": "DADO_PRIVADO_TESTE"})
    )


def push(host, state: LyraRunState) -> None:
    host._on_tool_state(state)


def test_m142_timeline_empty_and_immutable_snapshot() -> None:
    timeline = TaskTimeline()
    assert timeline.snapshot() == ()
    assert timeline.display() == TASK_TIMELINE_EMPTY
    assert TASK_TIMELINE_LIMIT == 12


def test_m142_timeline_records_presented_states_only() -> None:
    timeline = TaskTimeline()
    view = present_run_state(started())
    assert timeline.record(view)
    assert timeline.snapshot() == ("Tarefa: iniciada · 0/4 etapas",)
    assert timeline.display() == "1. Tarefa: iniciada · 0/4 etapas"


def test_m142_timeline_deduplicates_adjacent_events() -> None:
    timeline = TaskTimeline()
    view = present_run_state(started())
    assert timeline.record(view)
    assert not timeline.record(view)
    assert len(timeline.snapshot()) == 1


def test_m142_timeline_retains_only_last_twelve() -> None:
    timeline = TaskTimeline()
    for i in range(20):
        assert timeline.record(HostWorkflowProgressView(text=f"Tarefa: etapa {i}", terminal=False))
    assert len(timeline.snapshot()) == 12
    assert timeline.snapshot()[0] == "Tarefa: etapa 8"
    assert timeline.snapshot()[-1] == "Tarefa: etapa 19"
    assert timeline.display().startswith("1. Tarefa: etapa 8")


def test_m142_timeline_rejects_invalid_types_and_oversized_labels() -> None:
    timeline = TaskTimeline()
    assert not timeline.record("Tarefa: falso")  # type: ignore[arg-type]
    assert not timeline.record(HostWorkflowProgressView(text="X" * (TASK_TIMELINE_MAX_ENTRY_CHARS + 1), terminal=False))
    assert timeline.snapshot() == ()


def test_m142_timeline_rejects_control_characters() -> None:
    timeline = TaskTimeline()
    for label in ("Tarefa: a\nb", "Tarefa: a\tb", "Tarefa: a\x7fb"):
        assert not timeline.record(HostWorkflowProgressView(text=label, terminal=False))
    assert timeline.snapshot() == ()


def test_m142_timeline_clear_discards_all_events() -> None:
    timeline = TaskTimeline()
    assert timeline.record(present_run_state(started()))
    timeline.clear()
    assert timeline.snapshot() == () and timeline.display() == TASK_TIMELINE_EMPTY


def test_m142_panel_has_read_only_hidden_default(host) -> None:
    window, provider, _ = host
    assert window.task_timeline_toggle.objectName() == "lyra_task_timeline_toggle"
    assert window.task_timeline_view.objectName() == "lyra_task_timeline_view"
    assert window.task_timeline_view.isReadOnly()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
    assert provider.calls == 0


def test_m142_click_reveals_and_hides_panel(host) -> None:
    window, provider, _ = host
    window.show()
    QApplication.processEvents()
    window.task_timeline_toggle.click()
    assert not window.task_timeline_view.isHidden()
    window.task_timeline_toggle.click()
    assert window.task_timeline_view.isHidden()
    assert provider.calls == 0


def test_m142_state_updates_panel_and_current_status(host) -> None:
    window, provider, _ = host
    state = started()
    push(window, state)
    assert window.workflow_status.text() == present_run_state(state).text
    assert window.task_timeline_view.toPlainText() == "1. Tarefa: iniciada · 0/4 etapas"
    push(window, running())
    assert "system_status" in window.task_timeline_view.toPlainText()
    assert provider.calls == 0


def test_m142_repeated_host_state_is_idempotent(host) -> None:
    window, _, _ = host
    state = started()
    push(window, state)
    push(window, state)
    assert len(window._task_timeline.snapshot()) == 1


def test_m142_panel_available_while_busy(host) -> None:
    window, provider, _ = host
    push(window, started())
    window._set_busy(True)
    try:
        assert window.task_timeline_toggle.isEnabled()
        window.task_timeline_toggle.click()
        assert not window.task_timeline_view.isHidden()
        assert window.task_timeline_view.isReadOnly()
    finally:
        window._set_busy(False)
    assert provider.calls == 0


def test_m142_invalid_state_does_not_modify_timeline(host) -> None:
    window, provider, _ = host
    push(window, started())
    expected = window.task_timeline_view.toPlainText()
    window._on_tool_state({"status": "unsafe", "secret": "x"})
    assert window.task_timeline_view.toPlainText() == expected
    assert provider.calls == 0


def test_m142_panel_omits_intent_and_raw_action_arguments(host) -> None:
    window, provider, _ = host
    push(window, started())
    push(window, running())
    text = window.task_timeline_view.toPlainText()
    assert "Solicitação confidencial" not in text
    assert "DADO_PRIVADO_TESTE" not in text
    assert "secret" not in text
    assert "system_status" in text
    assert provider.calls == 0


def test_m142_reset_denied_retains_timeline(host, monkeypatch) -> None:
    window, provider, _ = host
    push(window, started())
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert len(window._task_timeline.snapshot()) == 1
    assert "iniciada" in window.task_timeline_view.toPlainText()
    assert provider.calls == 0


def test_m142_reset_accepted_clears_timeline(host, monkeypatch) -> None:
    window, provider, memory = host
    push(window, started())
    personality = window._personality.snapshot()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
    assert window._memory is memory
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m142_timeline_isolated_between_two_windows(host) -> None:
    window, provider, _ = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        push(window, started())
        assert len(window._task_timeline.snapshot()) == 1
        assert other._task_timeline.snapshot() == ()
        assert other.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m142_panel_preserves_draft_find_and_follow(host) -> None:
    window, provider, _ = host
    window.input.setText("meu rascunho")
    window.transcript_find.setText("minha busca")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window.chat_follow.setChecked(False)
    before = window._context.provider_snapshot()
    push(window, started())
    window.task_timeline_toggle.click()
    assert window.input.text() == "meu rascunho"
    assert window.transcript_find.text() == "minha busca"
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert not window.chat_follow.isChecked()
    assert window._context.provider_snapshot() == before
    assert provider.calls == 0


def test_m142_new_tool_task_clears_previous_timeline_without_running_worker(host) -> None:
    window, provider, _ = host
    push(window, started())
    class DryPool:
        count = 0
        def start(self, worker) -> None:
            self.count += 1
            assert worker is not None
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    window._start_tool_task("nova solicitação", ())
    assert dry.count == 1
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
    assert provider.calls == 0


def test_m142_timeline_never_mutates_provider_memory_or_context(host) -> None:
    window, provider, memory = host
    context = window._context.provider_snapshot()
    perception = window._perception
    personality = window._personality.snapshot()
    transcript = window.chat.toPlainText()
    push(window, running())
    window.task_timeline_toggle.click()
    assert window._context.provider_snapshot() == context
    assert window._perception is perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
