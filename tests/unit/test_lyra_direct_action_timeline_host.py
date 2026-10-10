from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import (
    TASK_TIMELINE_EMPTY,
    present_direct_action_progress,
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


def result(request: ActionRequest, *, success=True, dispatched=None, verified=None) -> ActionResult:
    return ActionResult(
        request_id=request.request_id,
        success=success,
        message="PRIVATE_RESULT_SHOULD_NOT_BE_IN_TIMELINE",
        evidence={"password": "PRIVATE_EVIDENCE"},
        effect_dispatched=dispatched,
        postcondition_verified=verified,
    )


def launch(window, *, name="open_application", secret="SECRET_PATH") -> ActionRequest:
    request = ActionRequest(action=name, arguments={"path": secret})
    window._start_action(request)
    return request


def test_m143_formatter_accepts_registered_shape_only() -> None:
    view = present_direct_action_progress("open_application")
    assert view is not None
    assert view.text == "Ação direta: solicitada · open_application"
    assert not view.terminal


def test_m143_formatter_rejects_unsafe_or_oversize_names() -> None:
    for name in ("", "Action", "a-b", "a\nPRIVATE", "é", "a" * 49, "a secret", "a/x"):
        assert present_direct_action_progress(name) is None


def test_m143_formatter_rejects_wrong_types() -> None:
    assert present_direct_action_progress(None) is None  # type: ignore[arg-type]
    assert present_direct_action_progress(123) is None  # type: ignore[arg-type]
    assert present_direct_action_progress("open_application", result={"success": True}) is None  # type: ignore[arg-type]


def test_m143_formatter_verified_postcondition_requires_explicit_evidence() -> None:
    request = ActionRequest(action="open_application")
    view = present_direct_action_progress("open_application", result=result(request, verified=True))
    assert view is not None
    assert view.terminal
    assert view.text == "Ação direta: pós-condição verificada · open_application"


def test_m143_formatter_dispatched_not_postcondition() -> None:
    request = ActionRequest(action="open_application")
    view = present_direct_action_progress("open_application", result=result(request, dispatched=True, verified=False))
    assert view is not None
    assert view.terminal
    assert "efeito despachado" in view.text
    assert "pós-condição não comprovada" in view.text


def test_m143_formatter_success_without_evidence_no_verified_claim() -> None:
    request = ActionRequest(action="open_application")
    view = present_direct_action_progress("open_application", result=result(request, success=True))
    assert view is not None
    assert "efeito não comprovado" in view.text
    assert "verificada" not in view.text


def test_m143_formatter_failure_precedes_any_claim_of_success() -> None:
    request = ActionRequest(action="open_application")
    view = present_direct_action_progress("open_application", result=result(request, success=False, verified=True, dispatched=True))
    assert view is not None
    assert "falha reportada" in view.text
    assert "verificada" not in view.text


def test_m143_host_start_records_only_action_id(host) -> None:
    window, provider, _, dry = host
    request = launch(window)
    assert len(dry.workers) == 1
    assert window._active_direct_action == (request.action, request.request_id)
    assert window._task_timeline.snapshot() == ("Ação direta: solicitada · open_application",)
    assert window.workflow_status.text() == window._task_timeline.snapshot()[0]
    assert "SECRET_PATH" not in window.task_timeline_view.toPlainText()
    assert provider.calls == 0


def test_m143_host_success_reports_verified_only_with_evidence(host) -> None:
    window, _, _, _ = host
    request = launch(window)
    window._on_action_result(result(request, verified=True))
    timeline = window.task_timeline_view.toPlainText()
    assert "pós-condição verificada" in timeline
    assert "PRIVATE_RESULT_SHOULD_NOT_BE_IN_TIMELINE" not in timeline
    assert "PRIVATE_EVIDENCE" not in timeline
    assert window.input.isEnabled()
    assert window._active_direct_action is None


def test_m143_host_failure_reports_failure_and_removes_pending(host) -> None:
    window, _, _, _ = host
    request = launch(window)
    window._on_action_result(result(request, success=False, dispatched=True))
    assert "falha reportada" in window.task_timeline_view.toPlainText()
    assert window._active_direct_action is None


def test_m143_host_mismatched_result_id_never_finishes_displayed_action(host) -> None:
    window, _, _, _ = host
    launch(window)
    other = ActionRequest(action="open_application")
    window._on_action_result(result(other, verified=True))
    assert len(window._task_timeline.snapshot()) == 1
    assert "verificada" not in window.task_timeline_view.toPlainText()
    assert window._active_direct_action is not None
    assert not window.input.isEnabled()


def test_m143_host_bad_action_name_fails_closed_without_raw_value(host) -> None:
    window, provider, _, dry = host
    launch(window, name="unexpected secret / file path")
    assert len(dry.workers) == 1
    assert window._task_timeline.snapshot() == ()
    assert window.task_timeline_view.toPlainText() == TASK_TIMELINE_EMPTY
    assert provider.calls == 0


def test_m143_new_direct_action_replaces_previous_timeline(host) -> None:
    window, _, _, dry = host
    first = launch(window)
    window._on_action_result(result(first))
    new = launch(window, name="system_status")
    assert len(dry.workers) == 2
    assert window._task_timeline.snapshot() == ("Ação direta: solicitada · system_status",)
    assert window._active_direct_action == (new.action, new.request_id)


def test_m143_denied_confirmation_does_not_start_or_modify_timeline(host, monkeypatch) -> None:
    window, provider, _, dry = host
    monkeypatch.setattr(window._actions, "risk_for", lambda *_: ActionRisk.CONFIRM)
    monkeypatch.setattr(window, "_confirm_action", lambda *_: False)
    window._handle_direct_action(ActionRequest(action="open_application", arguments={"application":"PRIVATE"}))
    assert len(dry.workers) == 0
    assert window._task_timeline.snapshot() == ()
    assert provider.calls == 0


def test_m143_busy_panel_remains_read_only_accessible(host) -> None:
    window, provider, _, _ = host
    launch(window)
    assert not window.input.isEnabled()
    assert window.task_timeline_toggle.isEnabled()
    assert window.task_timeline_view.isReadOnly()
    window.task_timeline_toggle.click()
    assert not window.task_timeline_view.isHidden()
    assert provider.calls == 0


def test_m143_host_no_context_memory_or_personality_mutation_on_start(host) -> None:
    window, provider, memory, _ = host
    before = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    launch(window)
    assert window._context.provider_snapshot() == before
    assert window._perception is perception
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert provider.calls == 0


def test_m143_separate_window_history_isolated(host) -> None:
    window, provider, _, _ = host
    other_provider = ControlledProvider()
    other = MainWindow(ActionRegistry(), object(), other_provider, build_default_tool_catalog())  # type: ignore[arg-type]
    try:
        launch(window)
        assert other._task_timeline.snapshot() == ()
        assert other._active_direct_action is None
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m143_approved_reset_clears_direct_action_state(host, monkeypatch) -> None:
    window, provider, memory, _ = host
    launch(window)
    window._set_busy(False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window._task_timeline.snapshot() == ()
    assert window._active_direct_action is None
    assert window._memory is memory
    assert provider.calls == 0


def test_m143_tool_loop_start_clears_prior_direct_action_identity(host) -> None:
    window, provider, _, dry = host
    direct_request = launch(window)
    window._set_busy(False)
    window._start_tool_task("new task", ())
    assert len(dry.workers) == 2
    assert window._active_direct_action is None
    assert window._task_timeline.snapshot() == ()
    assert not window.input.isEnabled()
    window._on_action_result(result(direct_request, verified=True))
    assert window._task_timeline.snapshot() == ()
    assert not window.input.isEnabled()
    assert window._active_control is not None
    assert provider.calls == 0


def test_m143_legacy_m142_timeline_still_accepts_normal_run_states(host) -> None:
    from theos.lyra.execution import LyraRunState
    window, provider, _, _ = host
    state = LyraRunState.start("hidden", max_steps=4)
    window._on_tool_state(state)
    assert window._task_timeline.snapshot() == ("Tarefa: iniciada · 0/4 etapas",)
    assert provider.calls == 0
