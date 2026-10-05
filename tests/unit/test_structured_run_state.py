from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import (
    AIContinuation,
    AIProviderError,
    AIReply,
    AIToolTurn,
)
from theos.lyra.execution import (
    LYRA_RUN_STATE_VERSION,
    ExecutionControl,
    LyraRunState,
    RunStatus,
    ToolLoopExecutor,
)


class TwoActionProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="open_application",
                    arguments={"application": "Notepad"},
                    call_id="call_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        if self.continuations == 1:
            return AIToolTurn(
                calls=(
                    ToolCall(
                        name="open_application",
                        arguments={"application": "Chrome"},
                        call_id="call_2",
                    ),
                ),
                continuation=AIContinuation(provider_id="fake", state=2),
                provider_id="fake",
            )
        return AIReply(text="Tudo pronto.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


class SensitiveProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="open_application",
                    arguments={"application": "PowerShell"},
                    call_id="sensitive_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(
            text="PowerShell aberto com autorização.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


class OneActionProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="open_application",
                    arguments={"application": "Notepad"},
                    call_id="one_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Concluído.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


class ErrorProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        raise AIProviderError("provedor indisponível")

    def continue_after_tools(self, turn, results):
        _ = turn, results
        raise AssertionError("no continuation expected")

    def reply(self, text, *, history=()):
        _ = text, history
        raise AssertionError("no reply expected")


def _register_open_application(
    registry: ActionRegistry,
    *,
    risk: ActionRisk = ActionRisk.NORMAL,
    success: bool = True,
) -> None:
    def handler(request: ActionRequest) -> ActionResult:
        application = str(request.arguments["application"])
        return ActionResult(
            request_id=request.request_id,
            success=success,
            message=(
                f"{application} aberto."
                if success
                else f"{application} falhou."
            ),
            evidence={
                "application": application,
                "verified": success,
            },
            error_code=None if success else "OPEN_FAILED",
            effect_dispatched=True,
            postcondition_verified=success,
        )

    registry.register(
        "open_application",
        handler,
        risk=risk,
    )


def test_run_state_tracks_goal_budget_and_action_evidence() -> None:
    state = LyraRunState.start(
        "  Abra o Bloco de Notas.  ",
        max_steps=4,
    )
    request = ActionRequest(
        action="open_application",
        arguments={"application": "Notepad"},
    )
    result = ActionResult(
        request_id=request.request_id,
        success=True,
        message="Notepad aberto.",
        evidence={"pid": 4321, "verified": True},
        effect_dispatched=True,
        postcondition_verified=True,
    )

    running = state.begin_action(request)
    recorded = running.record_action(request, result)
    completed = recorded.complete("Concluído.")

    assert state.version == LYRA_RUN_STATE_VERSION == 1
    assert state.goal == "Abra o Bloco de Notas."
    assert running.current_action == "open_application"
    assert recorded.completed_steps == 1
    assert recorded.remaining_step_budget == 3
    assert recorded.steps[0].evidence == {"pid": 4321, "verified": True}
    assert recorded.steps[0].effect_dispatched is True
    assert recorded.steps[0].postcondition_verified is True
    assert completed.status is RunStatus.COMPLETED
    assert not hasattr(completed, "goal_achieved")


def test_run_state_rejects_invalid_transitions_and_budget_overrun() -> None:
    state = LyraRunState.start("Faça algo.", max_steps=1)
    request = ActionRequest(action="open_application")
    result = ActionResult(
        request_id=request.request_id,
        success=True,
        message="ok",
    )

    with pytest.raises(ValueError):
        state.record_action(request, result)

    recorded = state.begin_action(request).record_action(request, result)

    with pytest.raises(ValueError):
        recorded.begin_action(ActionRequest(action="open_application"))

    with pytest.raises(ValueError):
        recorded.complete("   ")


def test_tool_loop_emits_structured_state_for_two_action_run() -> None:
    registry = ActionRegistry()
    _register_open_application(registry)
    catalog = build_default_tool_catalog()
    states: list[LyraRunState] = []

    result = ToolLoopExecutor(
        TwoActionProvider(),
        registry,
        catalog,
    ).execute(
        "Abra o Bloco de Notas e depois abra o Chrome.",
        tools=catalog.definitions(),
        state=states.append,
    )

    assert result.success is True
    assert result.run_state.status is RunStatus.COMPLETED
    assert result.run_state.goal == (
        "Abra o Bloco de Notas e depois abra o Chrome."
    )
    assert result.run_state.completed_steps == 2
    assert result.run_state.remaining_step_budget == 2
    assert [step.action for step in result.run_state.steps] == [
        "open_application",
        "open_application",
    ]
    assert [step.evidence["application"] for step in result.run_state.steps] == [
        "Notepad",
        "Chrome",
    ]
    assert states[0].status is RunStatus.RUNNING
    assert states[-1].status is RunStatus.COMPLETED
    assert states[-1].run_id == states[0].run_id
    assert any(
        item.current_action == "open_application"
        for item in states
    )


def test_run_state_identity_survives_confirmation_resume() -> None:
    registry = ActionRegistry()
    _register_open_application(registry, risk=ActionRisk.CONFIRM)
    catalog = build_default_tool_catalog()
    first_states: list[LyraRunState] = []

    executor = ToolLoopExecutor(
        SensitiveProvider(),
        registry,
        catalog,
    )
    waiting = executor.execute(
        "Abra o PowerShell.",
        tools=catalog.definitions(),
        state=first_states.append,
    )

    assert waiting.awaiting_confirmation is True
    assert waiting.run_state.status is RunStatus.AWAITING_CONFIRMATION
    assert waiting.run_state.current_action == "open_application"
    pending = waiting.pending_confirmation
    assert pending is not None
    assert pending.run_state.run_id == waiting.run_state.run_id

    resumed_states: list[LyraRunState] = []
    completed = executor.resume(
        pending,
        approved=True,
        state=resumed_states.append,
    )

    assert completed.success is True
    assert completed.run_state.status is RunStatus.COMPLETED
    assert completed.run_state.run_id == waiting.run_state.run_id
    assert completed.run_state.goal == waiting.run_state.goal
    assert completed.run_state.completed_steps == 1
    assert resumed_states[0].status is RunStatus.RUNNING
    assert resumed_states[0].current_action == "open_application"
    assert resumed_states[-1].status is RunStatus.COMPLETED


def test_rejected_confirmation_marks_run_cancelled_without_action_result() -> None:
    registry = ActionRegistry()
    _register_open_application(registry, risk=ActionRisk.CONFIRM)
    catalog = build_default_tool_catalog()
    executor = ToolLoopExecutor(
        SensitiveProvider(),
        registry,
        catalog,
    )

    waiting = executor.execute(
        "Abra o PowerShell.",
        tools=catalog.definitions(),
    )
    pending = waiting.pending_confirmation
    assert pending is not None

    cancelled = executor.resume(
        pending,
        approved=False,
    )

    assert cancelled.success is False
    assert cancelled.error == "Ação cancelada pelo usuário."
    assert cancelled.run_state.status is RunStatus.CANCELLED
    assert cancelled.run_state.completed_steps == 0
    assert cancelled.run_state.current_action is None


def test_control_cancellation_preserves_completed_structured_steps() -> None:
    registry = ActionRegistry()
    _register_open_application(registry)
    catalog = build_default_tool_catalog()
    control = ExecutionControl()

    def progress(message: str) -> None:
        if message == "Etapa 1: Notepad aberto.":
            control.cancel()

    result = ToolLoopExecutor(
        TwoActionProvider(),
        registry,
        catalog,
    ).execute(
        "Abra o Bloco de Notas e depois abra o Chrome.",
        tools=catalog.definitions(),
        control=control,
        progress=progress,
    )

    assert result.success is False
    assert result.run_state.status is RunStatus.CANCELLED
    assert result.run_state.completed_steps == 1
    assert result.run_state.steps[0].evidence["application"] == "Notepad"
    assert result.run_state.error == "Tarefa cancelada pelo usuário."


def test_failed_action_is_recorded_before_run_becomes_failed() -> None:
    registry = ActionRegistry()
    _register_open_application(registry, success=False)
    catalog = build_default_tool_catalog()

    result = ToolLoopExecutor(
        OneActionProvider(),
        registry,
        catalog,
    ).execute(
        "Abra o Bloco de Notas.",
        tools=catalog.definitions(),
    )

    assert result.success is False
    assert result.run_state.status is RunStatus.FAILED
    assert result.run_state.completed_steps == 1
    step = result.run_state.steps[0]
    assert step.success is False
    assert step.error_code == "OPEN_FAILED"
    assert step.effect_dispatched is True
    assert step.postcondition_verified is False


def test_provider_error_marks_run_failed_without_fabricating_steps() -> None:
    catalog = build_default_tool_catalog()

    result = ToolLoopExecutor(
        ErrorProvider(),
        ActionRegistry(),
        catalog,
    ).execute(
        "Explique algo usando as ferramentas.",
        tools=catalog.definitions(),
    )

    assert result.success is False
    assert result.run_state.status is RunStatus.FAILED
    assert result.run_state.completed_steps == 0
    assert result.run_state.steps == ()
    assert result.run_state.error == "provedor indisponível"
