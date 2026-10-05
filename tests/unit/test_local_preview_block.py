from __future__ import annotations

from theos.core.actions.contracts import (
    ActionRequest,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.tools import ToolCall
from theos.integrations.ai import AIContinuation, AIToolTurn
from theos.lyra.execution import (
    LyraRunState,
    PendingActionConfirmation,
    ToolLoopResult,
)
from theos.shell.assistant.main_window import MainWindow


class _BlockedPreviewRegistry:
    @staticmethod
    def confirmation_preview_for(
        request: ActionRequest,
    ) -> ConfirmationPreview:
        _ = request
        return ConfirmationPreview(
            allowed=False,
            text="Cópia bloqueada antes da confirmação: DESTINATION_ALREADY_EXISTS.",
        )


class _ConfirmationHarness:
    def __init__(self) -> None:
        self._actions = _BlockedPreviewRegistry()
        self.messages: list[str] = []

    @staticmethod
    def _action_subject(request: ActionRequest) -> str:
        return MainWindow._action_subject(request)

    def _lyra(self, text: str, *, remember_in_session: bool = False) -> None:
        _ = remember_in_session
        self.messages.append(text)


class _BlockedFlowHarness:
    def __init__(self) -> None:
        self.finished = False
        self.resumed = False

    @staticmethod
    def _confirm_action(
        request: ActionRequest,
        risk: ActionRisk,
    ) -> None:
        _ = request, risk

    def _resume_tool_loop(
        self,
        pending: PendingActionConfirmation,
        *,
        approved: bool,
    ) -> None:
        _ = pending, approved
        self.resumed = True

    def _finish_tool_task(self) -> None:
        self.finished = True

    def _lyra(self, text: str, *, remember_in_session: bool = False) -> None:
        raise AssertionError(
            f"blocked preview must not emit a fake cancellation: {text!r}, "
            f"remember={remember_in_session}"
        )


def _pending_result() -> ToolLoopResult:
    call = ToolCall(
        name="copy_path",
        arguments={
            "source": r"C:\Temp\a.txt",
            "destination": r"C:\Temp\b.txt",
        },
        call_id="copy_1",
    )
    turn = AIToolTurn(
        calls=(call,),
        continuation=AIContinuation(provider_id="fake", state=1),
        provider_id="fake",
    )
    request = ActionRequest(
        action="copy_path",
        arguments=dict(call.arguments),
    )
    run_state = LyraRunState.start(
        "Teste local de previa bloqueada.",
        max_steps=4,
    ).wait_for_confirmation(request)
    pending = PendingActionConfirmation(
        turn=turn,
        call=call,
        request=request,
        risk=ActionRisk.CONFIRM,
        completed_steps=0,
        run_state=run_state,
    )
    return ToolLoopResult(
        success=False,
        messages=(),
        final_reply=None,
        completed_steps=0,
        run_state=run_state,
        pending_confirmation=pending,
    )


def test_blocked_preview_is_distinct_from_user_denial() -> None:
    harness = _ConfirmationHarness()
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": r"C:\Temp\a.txt",
            "destination": r"C:\Temp\b.txt",
        },
    )

    decision = MainWindow._confirm_action(
        harness,
        request,
        ActionRisk.CONFIRM,
    )

    assert decision is None
    assert harness.messages == [
        (
            "Prévia local bloqueou a ação:\n"
            "Cópia bloqueada antes da confirmação: DESTINATION_ALREADY_EXISTS."
        )
    ]


def test_blocked_preview_finishes_without_resume_or_fake_user_cancel() -> None:
    harness = _BlockedFlowHarness()

    MainWindow._on_tool_loop_result(harness, _pending_result())

    assert harness.finished is True
    assert harness.resumed is False
