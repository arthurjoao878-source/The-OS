from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import (
    AIContinuation,
    AIReply,
    AIToolResult,
    AIToolTurn,
)
from theos.lyra.execution import ToolLoopExecutor


class TwoStepProvider:
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

    def continue_after_tools(
        self,
        turn: AIToolTurn,
        results: tuple[AIToolResult, ...],
    ):
        _ = turn
        self.continuations += 1
        assert results[0].output

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

        return AIReply(
            text="Tudo pronto.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_tool_loop_executes_next_action_after_verified_result() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        application = str(request.arguments["application"])
        executed.append(application)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"{application} aberto.",
            evidence={"verified": True},
        )

    registry.register("open_application", handler)
    provider = TwoStepProvider()
    executor = ToolLoopExecutor(
        provider,
        registry,
        build_default_tool_catalog(),
    )

    result = executor.execute(
        "Inicie o Bloco de Notas e depois o Google Chrome.",
        tools=build_default_tool_catalog().definitions(),
    )

    assert result.success is True
    assert result.completed_steps == 2
    assert executed == ["Notepad", "Chrome"]
    assert result.final_reply == "Tudo pronto."
    assert result.messages == (
        "Abrindo Notepad...",
        "Etapa 1: Notepad aberto.",
        "Abrindo Chrome...",
        "Etapa 2: Chrome aberto.",
    )


def test_tool_loop_stops_without_continuing_after_failed_action() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=False,
            message="Falhou.",
            error_code="ACTION_VERIFICATION_FAILED",
        )

    registry.register("open_application", handler)
    provider = TwoStepProvider()
    executor = ToolLoopExecutor(
        provider,
        registry,
        build_default_tool_catalog(),
    )

    result = executor.execute(
        "Abra dois aplicativos.",
        tools=build_default_tool_catalog().definitions(),
    )

    assert result.success is False
    assert result.completed_steps == 1
    assert provider.continuations == 0
    assert result.error == "Plano interrompido porque uma ação falhou na verificação."
