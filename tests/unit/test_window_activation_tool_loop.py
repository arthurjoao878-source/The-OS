from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class ActivateWindowProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="activate_window",
                    arguments={
                        "pid": 4321,
                        "title": "Documento - Bloco de Notas",
                    },
                    call_id="activate_window_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Janela ativada.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_activate_window_normal_action_executes_without_confirmation() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Janela ativada e verificada.",
            evidence={
                "pid": 4321,
                "title": "Documento - Bloco de Notas",
                "foreground_verified": True,
            },
        )

    registry.register(
        "activate_window",
        handler,
        risk=ActionRisk.NORMAL,
    )
    catalog = build_default_tool_catalog()
    provider = ActivateWindowProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    result = executor.execute(
        "Mude para o Bloco de Notas.",
        tools=catalog.definitions(),
    )

    assert result.success is True
    assert result.awaiting_confirmation is False
    assert result.completed_steps == 1
    assert result.final_reply == "Janela ativada."
    assert calls == 1
    assert provider.continuations == 1
