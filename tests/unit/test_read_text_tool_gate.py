from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.file_system import ReadTextFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class ReadProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="read_text_file",
                    arguments={"path": r"C:\Temp\notes.txt"},
                    call_id="read_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(text="Conteúdo recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_read_tool_does_not_touch_file_before_user_approval() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(str(request.arguments["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Arquivo lido.",
            evidence={"content": "safe", "content_is_untrusted_data": True},
        )

    registry.register(
        ReadTextFileAction.name,
        handler,
        risk=ReadTextFileAction.risk_for,
    )
    catalog = build_default_tool_catalog()
    provider = ReadProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Leia C:\\Temp\\notes.txt",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert executed == []
    assert provider.continuations == 0

    pending = waiting.pending_confirmation
    assert pending is not None
    cancelled = executor.resume(pending, approved=False)

    assert cancelled.success is False
    assert executed == []
    assert provider.continuations == 0
    assert cancelled.error == "Ação cancelada pelo usuário."
