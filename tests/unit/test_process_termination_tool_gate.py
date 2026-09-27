from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class TerminateProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="terminate_process",
                    arguments={"pid": 4321},
                    call_id="terminate_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Processo encerrado.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_catalog_builds_terminate_process_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(name="terminate_process", arguments={"pid": 4321})
    )

    assert request.action == "terminate_process"
    assert request.arguments == {"pid": 4321}


def test_terminate_process_waits_for_destructive_confirmation() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Processo encerrado e verificado: notepad.exe (PID 4321).",
            evidence={"pid": 4321, "verified_exited": True},
        )

    registry.register(
        "terminate_process",
        handler,
        risk=ActionRisk.DESTRUCTIVE,
    )
    catalog = build_default_tool_catalog()
    provider = TerminateProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Encerre o processo PID 4321.",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert calls == 0
    assert provider.continuations == 0

    pending = waiting.pending_confirmation
    assert pending is not None
    cancelled = executor.resume(pending, approved=False)

    assert cancelled.success is False
    assert calls == 0
    assert provider.continuations == 0
