from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class WindowProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="window_snapshot",
                    arguments={},
                    call_id="windows_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Janelas inspecionadas.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_catalog_builds_window_snapshot_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(name="window_snapshot", arguments={})
    )

    assert request.action == "window_snapshot"
    assert request.arguments == {}

    unfiltered_null = catalog.build_action_request(
        ToolCall(
            name="window_snapshot",
            arguments={"query": None},
        )
    )
    assert unfiltered_null.action == "window_snapshot"
    assert unfiltered_null.arguments == {}

    filtered = catalog.build_action_request(
        ToolCall(
            name="window_snapshot",
            arguments={"query": " Bloco de Notas "},
        )
    )
    assert filtered.action == "window_snapshot"
    assert filtered.arguments == {"query": "Bloco de Notas"}


def test_window_snapshot_waits_for_confirmation_and_denial_does_not_enumerate() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Janelas inspecionadas.",
            evidence={"returned_windows": 0, "windows": []},
        )

    registry.register(
        "window_snapshot",
        handler,
        risk=ActionRisk.CONFIRM,
    )
    catalog = build_default_tool_catalog()
    provider = WindowProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Quais janelas estão abertas?",
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
