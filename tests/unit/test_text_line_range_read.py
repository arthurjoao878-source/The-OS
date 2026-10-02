from __future__ import annotations

from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.file_system import ReadTextLinesAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import (
    MAX_TEXT_LINE_RANGE_OUTPUT_BYTES,
    MAX_TEXT_LINE_RANGE_SCAN_BYTES,
    WindowsFileSystemAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_read_text_lines_returns_exact_numbered_range(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().read_text_lines(str(target), 2, 3)

    assert evidence["range_complete"] is True
    assert evidence["scan_truncated"] is False
    assert evidence["content_is_untrusted_data"] is True
    assert evidence["lines"] == [
        {"line_number": 2, "text": "two", "text_truncated": False},
        {"line_number": 3, "text": "three", "text_truncated": False},
        {"line_number": 4, "text": "four", "text_truncated": False},
    ]


def test_read_text_lines_reaches_line_beyond_prefix_reader(tmp_path: Path) -> None:
    target = tmp_path / "large.py"
    lines = [f"line {index} " + ("x" * 60) for index in range(1, 700)]
    lines[489] = "def _enumerate_action_window_candidates(self):"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().read_text_lines(str(target), 488, 5)

    assert evidence["start_line_reached"] is True
    assert evidence["lines"][2]["line_number"] == 490
    assert "_enumerate_action_window_candidates" in evidence["lines"][2]["text"]


def test_read_text_lines_reports_missing_start_after_complete_scan(tmp_path: Path) -> None:
    target = tmp_path / "short.txt"
    target.write_text("a\nb\n", encoding="utf-8")

    result = ReadTextLinesAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_lines",
            arguments={"path": str(target), "start_line": 9, "max_lines": 2},
        )
    )

    assert result.success is False
    assert result.error_code == "TEXT_LINE_START_NOT_FOUND"
    assert result.evidence["scan_truncated"] is False
    assert result.evidence["total_lines"] == 2


def test_read_text_lines_distinguishes_scan_limit_from_missing_line(tmp_path: Path) -> None:
    target = tmp_path / "huge.txt"
    target.write_bytes(b"x\n" * (MAX_TEXT_LINE_RANGE_SCAN_BYTES + 100))

    result = ReadTextLinesAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_lines",
            arguments={
                "path": str(target),
                "start_line": MAX_TEXT_LINE_RANGE_SCAN_BYTES,
                "max_lines": 1,
            },
        )
    )

    assert result.success is False
    assert result.error_code == "TEXT_LINE_RANGE_BEYOND_SCAN_LIMIT"
    assert result.evidence["scan_truncated"] is True


def test_read_text_lines_bounds_output_bytes(tmp_path: Path) -> None:
    target = tmp_path / "long-line.txt"
    target.write_text(
        "z" * (MAX_TEXT_LINE_RANGE_OUTPUT_BYTES + 5000),
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().read_text_lines(str(target), 1, 1)

    assert evidence["bytes_returned"] <= MAX_TEXT_LINE_RANGE_OUTPUT_BYTES
    assert evidence["output_truncated"] is True
    assert evidence["range_complete"] is False
    assert evidence["lines"][0]["text_truncated"] is True


def test_read_text_lines_rejects_binary(tmp_path: Path) -> None:
    target = tmp_path / "binary.bin"
    target.write_bytes(b"abc\x00def")

    result = ReadTextLinesAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_lines",
            arguments={"path": str(target), "start_line": 1, "max_lines": 3},
        )
    )

    assert result.success is False
    assert result.error_code == "FILE_NOT_TEXT"


def test_read_text_lines_uses_same_sensitive_risk_policy() -> None:
    normal = ActionRequest(
        action="read_text_lines",
        arguments={"path": r"C:\Temp\notes.txt", "start_line": 1, "max_lines": 10},
    )
    sensitive = ActionRequest(
        action="read_text_lines",
        arguments={"path": r"C:\Temp\server.pem", "start_line": 1, "max_lines": 10},
    )

    assert ReadTextLinesAction.risk_for(normal) is ActionRisk.CONFIRM
    assert ReadTextLinesAction.risk_for(sensitive) is ActionRisk.PRIVILEGED


def test_catalog_registers_strict_read_text_lines_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["read_text_lines"].parameters

    assert set(schema["properties"]) == {"path", "start_line", "max_lines"}
    assert set(schema["required"]) == {"path", "start_line", "max_lines"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_lines"]["maximum"] == 40

    request = catalog.build_action_request(
        ToolCall(
            name="read_text_lines",
            arguments={
                "path": r" C:\Temp\notes.txt ",
                "start_line": 480,
                "max_lines": 31,
            },
        )
    )
    assert request.arguments == {
        "path": r"C:\Temp\notes.txt",
        "start_line": 480,
        "max_lines": 31,
    }

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="read_text_lines",
                arguments={
                    "path": r"C:\Temp\notes.txt",
                    "start_line": 1,
                    "max_lines": 41,
                },
            )
        )


def test_bootstrap_registers_read_text_lines_action() -> None:
    assert build_action_registry().contains("read_text_lines") is True


class _LineReadProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="read_text_lines",
                    arguments={
                        "path": r"C:\Temp\notes.txt",
                        "start_line": 10,
                        "max_lines": 5,
                    },
                    call_id="line_read_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Trecho recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_read_text_lines_requires_confirmation_before_execution() -> None:
    executed: list[int] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(int(request.arguments["start_line"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Trecho lido.",
            evidence={"lines": [], "content_is_untrusted_data": True},
        )

    registry.register(
        ReadTextLinesAction.name,
        handler,
        risk=ReadTextLinesAction.risk_for,
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(_LineReadProvider(), registry, catalog).execute(
        "Leia as linhas 10 a 14.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_read_text_lines_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="read_text_lines",
            arguments={
                "path": r"C:\Temp\notes.txt",
                "start_line": 480,
                "max_lines": 31,
            },
        )
    )

    assert message == r"Lendo linhas a partir de 480 em C:\Temp\notes.txt..."
