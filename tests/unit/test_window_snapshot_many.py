from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.desktop_windows import WindowSnapshotManyAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import (
    ToolCall,
    ToolValidationError,
    build_default_tool_catalog,
)
from theos.core.window_targets import normalize_window_queries
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.lyra.execution import ToolLoopExecutor


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.snapshot_many_calls = 0
        self.snapshot_many_queries: list[tuple[str, ...]] = []

    def snapshot_many(
        self,
        queries: tuple[str, ...],
    ) -> dict[str, object]:
        self.snapshot_many_calls += 1
        self.snapshot_many_queries.append(queries)
        rows = [
            {
                "title": "Documento - Bloco de Notas",
                "pid": 100,
                "process_name": "notepad.exe",
                "target_token": "1" * 64,
            },
            {
                "title": "THE OS — LYRA",
                "pid": 300,
                "process_name": "python.exe",
                "target_token": "3" * 64,
            },
        ]
        return {
            "observed_windows": 18,
            "matched_windows": 2,
            "returned_windows": 2,
            "max_results": 12,
            "max_title_chars": 160,
            "filter_applied": True,
            "filter_queries": list(queries),
            "filter_count": len(queries),
            "filter_mode": "any_query",
            "filter_match": "casefold_substring_title_or_process_name",
            "query_match_counts": {
                queries[0]: 1,
                queries[1]: 1,
            },
            "order": "windows_z_order_within_multi_filter",
            "fields": ["title", "pid", "process_name", "target_token"],
            "windows": rows,
        }


def test_window_snapshot_many_preview_is_static_and_privacy_gated() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotManyAction(adapter)
    request = ActionRequest(
        action="window_snapshot_many",
        arguments={"queries": ["Bloco de Notas", "LYRA"]},
    )

    assert action.risk is ActionRisk.CONFIRM
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "INSPECIONAR MÚLTIPLAS JANELAS VISÍVEIS" in preview.text
    assert "Bloco de Notas; LYRA" in preview.text
    assert "12 janelas" in preview.text
    assert "capturas de tela" in preview.text
    assert adapter.snapshot_many_calls == 0


def test_window_snapshot_many_executes_single_adapter_contract() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotManyAction(adapter)
    request = ActionRequest(
        action="window_snapshot_many",
        arguments={"queries": [" Bloco de Notas ", " LYRA "]},
    )

    result = action.execute(request)

    assert result.success is True
    assert adapter.snapshot_many_calls == 1
    assert adapter.snapshot_many_queries == [("Bloco de Notas", "LYRA")]
    assert result.evidence["filter_count"] == 2
    assert result.evidence["filter_mode"] == "any_query"
    assert result.evidence["returned_windows"] == 2
    assert "2 filtros locais" in result.message


def test_catalog_builds_multi_query_snapshot_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="window_snapshot_many",
            arguments={
                "queries": [" Bloco de Notas ", " LYRA "],
            },
        )
    )

    assert request.action == "window_snapshot_many"
    assert request.arguments == {
        "queries": ["Bloco de Notas", "LYRA"],
    }

    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["window_snapshot_many"].parameters
    assert schema["properties"]["queries"]["minItems"] == 2
    assert schema["properties"]["queries"]["maxItems"] == 4
    assert schema["required"] == ["queries"]
    assert schema["additionalProperties"] is False


def test_catalog_rejects_invalid_multi_query_sets() -> None:
    catalog = build_default_tool_catalog()
    invalid_sets = (
        ["Bloco de Notas"],
        ["a", "b", "c", "d", "e"],
        ["Bloco de Notas", " bloco de notas "],
        ["Bloco de Notas", ""],
        ["Bloco de Notas", "\n"],
    )

    for queries in invalid_sets:
        try:
            catalog.build_action_request(
                ToolCall(
                    name="window_snapshot_many",
                    arguments={"queries": queries},
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid multi-query set must be rejected")


class _ManyWindowProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="window_snapshot_many",
                    arguments={"queries": ["Bloco de Notas", "LYRA"]},
                    call_id="windows_many_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(
            text="Janelas solicitadas inspecionadas.",
            provider_id="fake",
        )

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_multi_query_snapshot_waits_for_confirmation_and_denial_does_not_enumerate() -> None:
    calls = 0
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Janelas solicitadas inspecionadas.",
            evidence={"returned_windows": 0, "windows": []},
        )

    registry.register(
        "window_snapshot_many",
        handler,
        risk=ActionRisk.CONFIRM,
    )
    catalog = build_default_tool_catalog()
    provider = _ManyWindowProvider()
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Inspecione apenas o Bloco de Notas e a LYRA.",
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


def test_multi_query_normalization_is_casefold_distinct_and_bounded() -> None:
    assert normalize_window_queries(
        [" Bloco de Notas ", " LYRA "]
    ) == ("Bloco de Notas", "LYRA")
    assert normalize_window_queries(["A", "B", "C", "D"]) == (
        "A",
        "B",
        "C",
        "D",
    )
    assert normalize_window_queries(["A"]) is None
    assert normalize_window_queries(["A", "B", "C", "D", "E"]) is None
    assert normalize_window_queries(["LYRA", " lyra "]) is None
    assert normalize_window_queries(["A", ""]) is None
