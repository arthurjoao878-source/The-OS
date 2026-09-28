from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class PressKeyProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="press_key",
                    arguments={
                        "pid": 4321,
                        "title": "Sem título - Bloco de Notas",
                        "key": "ENTER",
                    },
                    call_id="press_key_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Tecla enviada.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_press_key_waits_for_confirmation() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Tecla ENTER enviada.",
            evidence={
                "pid": 4321,
                "title": "Sem título - Bloco de Notas",
                "key": "ENTER",
                "input_submission_verified": True,
                "content_effect_verified": False,
            },
        )

    registry.register(
        "press_key",
        handler,
        risk=ActionRisk.CONFIRM,
    )
    catalog = build_default_tool_catalog()
    provider = PressKeyProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Pressione Enter no Bloco de Notas.",
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
