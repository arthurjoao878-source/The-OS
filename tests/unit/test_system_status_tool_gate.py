from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class SystemStatusProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="system_status",
                    arguments={},
                    call_id="status_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn
        assert len(results) == 1
        self.continuations += 1
        return AIReply(
            text="O computador está com uso moderado.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_catalog_builds_system_status_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(name="system_status", arguments={})
    )

    assert request.action == "system_status"
    assert request.arguments == {}


def test_system_status_tool_executes_without_confirmation() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Status do sistema coletado: CPU 10.0%, memória 20.0%, disco 30.0%.",
            evidence={
                "cpu_percent": 10.0,
                "memory_percent": 20.0,
                "disk_percent": 30.0,
            },
        )

    registry.register("system_status", handler, risk=ActionRisk.READ_ONLY)
    catalog = build_default_tool_catalog()
    provider = SystemStatusProvider()

    result = ToolLoopExecutor(provider, registry, catalog).execute(
        "Como está o uso do meu computador agora?",
        tools=catalog.definitions(),
    )

    assert result.success is True
    assert result.awaiting_confirmation is False
    assert result.messages == (
        "Coletando status do sistema...",
        (
            "Etapa 1: Status do sistema coletado: "
            "CPU 10.0%, memória 20.0%, disco 30.0%."
        ),
    )
    assert result.final_reply == "O computador está com uso moderado."
    assert provider.continuations == 1
