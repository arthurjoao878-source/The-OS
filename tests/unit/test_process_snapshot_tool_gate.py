from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class ProcessProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="process_snapshot",
                    arguments={},
                    call_id="process_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Os processos com maior uso de memória foram identificados.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_catalog_builds_process_snapshot_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(name="process_snapshot", arguments={})
    )

    assert request.action == "process_snapshot"
    assert request.arguments == {}


def test_process_snapshot_waits_for_confirmation_before_enumeration() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Processos inspecionados: 2 observados; 2 retornados.",
            evidence={
                "observed_processes": 2,
                "returned_processes": 2,
                "processes": [],
            },
        )

    registry.register(
        "process_snapshot",
        handler,
        risk=ActionRisk.CONFIRM,
    )
    catalog = build_default_tool_catalog()
    provider = ProcessProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Quais processos estão usando mais memória?",
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
