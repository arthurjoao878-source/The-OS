from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class TypeTextProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="type_text",
                    arguments={
                        "pid": 4321,
                        "title": "M28-LIVE.txt - Bloco de Notas",
                        "target_token": "d" * 64,
                        "text": "Olá, LYRA!",
                    },
                    call_id="type_text_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Texto enviado.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_type_text_waits_for_confirmation() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Entrada de texto enviada.",
            evidence={
                "pid": 4321,
                "title": "M28-LIVE.txt - Bloco de Notas",
                "target_token": "d" * 64,
                "input_submission_verified": True,
                "content_effect_verified": False,
            },
        )

    registry.register(
        "type_text",
        handler,
        risk=ActionRisk.CONFIRM,
    )
    catalog = build_default_tool_catalog()
    provider = TypeTextProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Digite Olá, LYRA! no Bloco de Notas.",
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
