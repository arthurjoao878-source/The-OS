from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.execution import ExecutionStatus, LyraRunState
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import (
    TASK_TIMELINE_EMPTY,
    TASK_TIMELINE_LIMIT,
    TaskInterruptionKind,
    TaskTimeline,
    present_task_interruption,
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
        raise AssertionError("unexpected provider continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected provider reply")


class DryPool:
    def __init__(self) -> None:
        self.workers: list[object] = []

    def start(self, worker) -> None:
        self.workers.append(worker)


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
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def launch(window: MainWindow) -> None:
    window._start_tool_task("PRIVATE_INTENT_NEVER_IN_TIMELINE", ())


def test_m144_kind_is_finite() -> None:
    assert set(TaskInterruptionKind) == {
        TaskInterruptionKind.CANCEL_REQUESTED,
        TaskInterruptionKind.PROCESSING_FAILED,
        TaskInterruptionKind.INVALID_RESULT,
    }


def test_m144_cancellation_requested_is_nonterminal() -> None:
    view = present_task_interruption(TaskInterruptionKind.CANCEL_REQUESTED)
    assert view is not None
    assert view.text == "Tarefa: cancelamento solicitado · aguardando confirmação"
    assert view.terminal is False
    assert "cancelada" not in view.text


def test_m144_processing_failure_is_terminal_without_effect_claim() -> None:
    view = present_task_interruption(TaskInterruptionKind.PROCESSING_FAILED)
    assert view is not None
    assert view.text == "Tarefa: falha no processamento · efeito não comprovado"
    assert view.terminal is True


def test_m144_invalid_result_is_terminal_without_effect_claim() -> None:
    view = present_task_interruption(TaskInterruptionKind.INVALID_RESULT)
    assert view is not None
    assert view.text == "Tarefa: resultado inválido · efeito não comprovado"
    assert view.terminal is True


def test_m144_unknown_or_untrusted_kind_fails_closed() -> None:
    for untrusted in (None, "CANCEL_REQUESTED", 0, {"kind": "PROCESSING_FAILED"}):
        assert present_task_interruption(untrusted) is None  # type: ignore[arg-type]


def test_m144_events_have_bounded_fixed_labels() -> None:
    for kind in TaskInterruptionKind:
        view = present_task_interruption(kind)
        assert view is not None
        assert len(view.text) <= 180
        assert all(ord(char) >= 32 and ord(char) != 127 for char in view.text)
        assert "PRIVATE_INTENT" not in view.text


def test_m144_timeline_records_and_deduplicates_interruption() -> None:
    timeline = TaskTimeline()
    view = present_task_interruption(TaskInterruptionKind.CANCEL_REQUESTED)
    assert view is not None
    assert timeline.record(view)
    assert not timeline.record(view)
    assert len(timeline.snapshot()) == 1


def test_m144_timeline_limit_preserved_with_interruption() -> None:
    timeline = TaskTimeline()
    from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

    for index in range(20):
        view = HostWorkflowProgressView(text=f"Tarefa: etapa {index}", terminal=False)
        assert timeline.record(view)
    view = present_task_interruption(TaskInterruptionKind.PROCESSING_FAILED)
    assert view is not None and timeline.record(view)
    assert len(timeline.snapshot()) == TASK_TIMELINE_LIMIT == 12
    assert timeline.snapshot()[-1] == view.text


def test_m144_idle_cancel_does_not_modify_status(host) -> None:
    window, provider, _, _ = host
    window._cancel_active_task()
    assert window._task_timeline.snapshot() == ()
    assert window.workflow_status.text() == "Tarefa: ociosa"
    assert provider.calls == 0


def test_m144_cancel_request_during_active_task_is_nonterminal(host) -> None:
    window, provider, _, dry = host
    launch(window)
    assert len(dry.workers) == 1
    window._cancel_active_task()
    assert window._active_control is not None
    assert window._active_control.status is ExecutionStatus.CANCELLED
    assert window._task_timeline.snapshot() == (
        "Tarefa: cancelamento solicitado · aguardando confirmação",
    )
    assert not window.input.isEnabled()
    assert provider.calls == 0


def test_m144_repeated_cancel_does_not_duplicate_event(host) -> None:
    window, provider, _, _ = host
    launch(window)
    window._cancel_active_task()
    window._cancel_active_task()
    assert len(window._task_timeline.snapshot()) == 1
    assert provider.calls == 0


def test_m144_cancel_from_paused_task_has_same_semantics(host) -> None:
    window, _, _, _ = host
    launch(window)
    window._pause_active_task()
    assert window._active_control is not None
    assert window._active_control.status is ExecutionStatus.PAUSED
    window._cancel_active_task()
    assert window._active_control.status is ExecutionStatus.CANCELLED
    assert "solicitado" in window.task_timeline_view.toPlainText()


def test_m144_terminal_cancel_state_is_only_real_confirmation(host) -> None:
    window, provider, _, _ = host
    launch(window)
    window._cancel_active_task()
    final = LyraRunState.start("PRIVATE_GOAL", max_steps=4).cancel("PRIVATE_REASON")
    window._on_tool_state(final)
    snapshot = window._task_timeline.snapshot()
    assert snapshot[0].startswith("Tarefa: cancelamento solicitado")
    assert snapshot[-1] == "Tarefa: cancelada · 0/4 etapas"
    assert "PRIVATE_GOAL" not in window.task_timeline_view.toPlainText()
    assert "PRIVATE_REASON" not in window.task_timeline_view.toPlainText()
    assert provider.calls == 0


def test_m144_real_failed_state_remains_original_m103_summary(host) -> None:
    window, _, _, _ = host
    launch(window)
    failed = LyraRunState.start("PRIVATE_GOAL", max_steps=4).fail("PRIVATE_FAILURE")
    window._on_tool_state(failed)
    assert window._task_timeline.snapshot() == ("Tarefa: falhou · 0/4 etapas",)
    assert "PRIVATE_FAILURE" not in window.task_timeline_view.toPlainText()


def test_m144_worker_failure_is_recorded_without_raw_message(host) -> None:
    window, provider, memory, _ = host
    launch(window)
    before = window._context.provider_snapshot()
    window._on_ai_failure("PRIVATE_PROVIDER_ERROR_AND_FILE_CONTENT")
    assert window._task_timeline.snapshot() == (
        "Tarefa: falha no processamento · efeito não comprovado",
    )
    assert "PRIVATE_PROVIDER_ERROR" not in window.task_timeline_view.toPlainText()
    assert window._active_control is None
    assert window.input.isEnabled()
    assert window._memory is memory
    assert window._context.provider_snapshot() == before
    assert provider.calls == 0


def test_m144_failure_without_active_task_does_not_invent_timeline(host) -> None:
    window, provider, _, _ = host
    window._on_ai_failure("PRIVATE_ERROR")
    assert window._task_timeline.snapshot() == ()
    assert window.workflow_status.text() == "Tarefa: ociosa"
    assert provider.calls == 0


def test_m144_invalid_worker_result_has_bounded_terminal_label(host) -> None:
    window, provider, _, _ = host
    launch(window)
    window._on_tool_loop_result({"result": "PRIVATE_FAKE_RESULT"})
    assert window._task_timeline.snapshot() == (
        "Tarefa: resultado inválido · efeito não comprovado",
    )
    assert "PRIVATE_FAKE_RESULT" not in window.task_timeline_view.toPlainText()
    assert window._active_control is None
    assert window.input.isEnabled()
    assert provider.calls == 0


def test_m144_invalid_result_without_active_task_no_record(host) -> None:
    window, provider, _, _ = host
    window._on_tool_loop_result(object())
    assert window._task_timeline.snapshot() == ()
    assert window.workflow_status.text() == "Tarefa: ociosa"
    assert provider.calls == 0


def test_m144_busy_panel_remains_read_only_and_clickable(host) -> None:
    window, provider, _, _ = host
    launch(window)
    window._cancel_active_task()
    assert window.task_timeline_view.isReadOnly()
    assert window.task_timeline_toggle.isEnabled()
    window.task_timeline_toggle.click()
    assert not window.task_timeline_view.isHidden()
    assert provider.calls == 0


def test_m144_cancel_does_not_change_draft_search_follow_or_personality(host) -> None:
    window, provider, _, _ = host
    window.input.setText("PRIVATE_DRAFT")
    window.transcript_find.setText("PRIVATE_SEARCH")
    window.chat_follow.setChecked(False)
    personality = window._personality.snapshot()
    launch(window)
    window._cancel_active_task()
    assert window.input.text() == "PRIVATE_DRAFT"
    assert window.transcript_find.text() == "PRIVATE_SEARCH"
    assert window.chat_follow.isChecked() is False
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m144_second_task_clears_prior_failure_summary(host) -> None:
    window, provider, _, dry = host
    launch(window)
    window._on_ai_failure("PRIVATE_ERROR")
    launch(window)
    assert window._task_timeline.snapshot() == ()
    assert len(dry.workers) == 2
    assert provider.calls == 0


def test_m144_each_host_has_independent_interruption_timeline(host) -> None:
    window, provider, _, _ = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(),  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        launch(window)
        window._cancel_active_task()
        assert other._task_timeline.snapshot() == ()
        assert other.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m144_denied_reset_preserves_interruption(host, monkeypatch) -> None:
    window, provider, _, _ = host
    launch(window)
    window._cancel_active_task()
    window._set_busy(False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    assert len(window._task_timeline.snapshot()) == 1
    assert provider.calls == 0


def test_m144_approved_reset_clears_interruption(host, monkeypatch) -> None:
    window, provider, memory, _ = host
    launch(window)
    window._cancel_active_task()
    window._set_busy(False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
    assert window._memory is memory
    assert provider.calls == 0


def test_m144_no_provider_calls_or_real_action_execution(host) -> None:
    window, provider, memory, dry = host
    before = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    launch(window)
    window._cancel_active_task()
    assert len(dry.workers) == 1
    assert window._context.provider_snapshot() == before
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert provider.calls == 0
