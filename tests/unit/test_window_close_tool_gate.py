from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class CloseWindowProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="close_window",
                    arguments={
                        "pid": 4321,
                        "title": "M31-LIVE - Bloco de Notas",
                        "target_token": "c" * 64,
                    },
                    call_id="close_window_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Janela fechada.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_close_window_waits_for_destructive_confirmation() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Janela exata fechada e verificada.",
            evidence={
                "pid": 4321,
                "title": "M31-LIVE - Bloco de Notas",
                "target_token": "c" * 64,
                "window_gone_verified": True,
            },
        )

    registry.register(
        "close_window",
        handler,
        risk=ActionRisk.DESTRUCTIVE,
    )
    catalog = build_default_tool_catalog()
    provider = CloseWindowProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Feche a janela M31-LIVE do Bloco de Notas.",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert calls == 0
    assert provider.continuations == 0

    pending = waiting.pending_confirmation
    assert pending is not None
    denied = executor.resume(pending, approved=False)

    assert denied.success is False
    assert calls == 0
    assert provider.continuations == 0
