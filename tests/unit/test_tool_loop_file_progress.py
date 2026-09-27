from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class InspectProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="inspect_path",
                    arguments={"path": r"C:\Temp"},
                    call_id="inspect_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Inspeção concluída.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_tool_loop_uses_action_specific_file_progress_message() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Pasta inspecionada: Temp.",
            evidence={"path": r"C:\Temp", "exists": True, "kind": "directory"},
        )

    registry.register("inspect_path", handler, risk=ActionRisk.READ_ONLY)
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        InspectProvider(),
        registry,
        catalog,
    ).execute(
        "Inspecione C:\\Temp.",
        tools=catalog.definitions(),
    )

    assert result.success is True
    assert result.messages == (
        r"Inspecionando C:\Temp...",
        "Etapa 1: Pasta inspecionada: Temp.",
    )
    assert result.final_reply == "Inspeção concluída."
