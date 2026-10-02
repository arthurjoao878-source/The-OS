from __future__ import annotations

from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.file_system import SearchTextAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import (
    MAX_TEXT_SEARCH_BYTES_PER_FILE,
    MAX_TEXT_SEARCH_QUERY_CHARS,
    WindowsFileSystemAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_text_search_finds_casefold_literal_with_line_evidence(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        "alpha\nShared Resolver Here\nomega\n",
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().search_text(
        str(tmp_path),
        "shared resolver",
    )

    assert evidence["complete"] is True
    assert evidence["content_is_untrusted_data"] is True
    assert evidence["matches"] == [
        {
            "path": str(source.resolve()),
            "relative_path": "module.py",
            "line_number": 2,
            "snippet": "Shared Resolver Here",
            "snippet_truncated": False,
            "file_prefix_only": False,
        }
    ]


def test_search_action_skips_known_privileged_read_paths(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("needle=secret", encoding="utf-8")
    safe = tmp_path / "module.py"
    safe.write_text("needle = 'safe'\n", encoding="utf-8")

    result = SearchTextAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="search_text",
            arguments={"root": str(tmp_path), "query": "needle"},
        )
    )

    assert result.success is True
    assert result.evidence["skipped_sensitive_files"] == 1
    assert result.evidence["complete"] is False
    assert [match["path"] for match in result.evidence["matches"]] == [
        str(safe.resolve())
    ]


def test_text_search_ignores_binary_files(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"needle\x00payload")
    (tmp_path / "plain.txt").write_text("needle\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().search_text(
        str(tmp_path),
        "needle",
    )

    assert evidence["skipped_binary_files"] == 1
    assert len(evidence["matches"]) == 1
    assert evidence["matches"][0]["relative_path"] == "plain.txt"


def test_text_search_marks_large_prefix_scan_partial(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_bytes(
        b"a" * MAX_TEXT_SEARCH_BYTES_PER_FILE + b"\nneedle-after-limit\n"
    )

    evidence = WindowsFileSystemAdapter().search_text(
        str(tmp_path),
        "needle-after-limit",
    )

    assert evidence["matches"] == []
    assert evidence["partial_files"] == 1
    assert evidence["complete"] is False


def test_text_search_preview_is_static_and_bounded() -> None:
    class ExplodingAdapter:
        def search_text(self, *args, **kwargs):
            raise AssertionError("preview must not touch filesystem")

    action = SearchTextAction(ExplodingAdapter())
    preview = action.confirmation_preview(
        ActionRequest(
            action="search_text",
            arguments={"root": r"C:\Projetos", "query": "needle"},
        )
    )

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "PESQUISAR TEXTO EM ARQUIVOS" in preview.text
    assert "não usa regex/fuzzy" in preview.text


def test_catalog_registers_strict_search_text_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["search_text"].parameters

    assert set(schema["properties"]) == {"root", "query"}
    assert set(schema["required"]) == {"root", "query"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["query"]["maxLength"] == MAX_TEXT_SEARCH_QUERY_CHARS

    request = catalog.build_action_request(
        ToolCall(
            name="search_text",
            arguments={"root": r" C:\Projetos ", "query": " needle "},
        )
    )
    assert request.arguments == {
        "root": r"C:\Projetos",
        "query": "needle",
    }

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="search_text",
                arguments={
                    "root": r"C:\Projetos",
                    "query": "x" * (MAX_TEXT_SEARCH_QUERY_CHARS + 1),
                },
            )
        )


def test_bootstrap_registers_search_text_action() -> None:
    assert build_action_registry().contains("search_text") is True


class _SearchProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="search_text",
                    arguments={"root": r"C:\Projetos", "query": "needle"},
                    call_id="search_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Busca recebida.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_text_search_tool_requires_confirmation_before_execution() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(str(request.arguments["query"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Busca concluída.",
            evidence={"matches": [], "content_is_untrusted_data": True},
        )

    preview_action = SearchTextAction(WindowsFileSystemAdapter())
    registry.register(
        "search_text",
        handler,
        risk=SearchTextAction.risk,
        confirmation_preview=preview_action.confirmation_preview,
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _SearchProvider(),
        registry,
        catalog,
    ).execute(
        "Procure needle em C:\\Projetos.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_text_search_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="search_text",
            arguments={"root": r"C:\Projetos", "query": "needle"},
        )
    )

    assert message == r"Procurando texto needle em C:\Projetos..."
