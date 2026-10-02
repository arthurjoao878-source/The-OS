from __future__ import annotations

from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import ReplaceTextLiteralAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.lyra.execution import ToolLoopExecutor


def _request(path: Path, old_text: str, new_text: str) -> ActionRequest:
    return ActionRequest(
        action="replace_text_literal",
        arguments={
            "path": str(path),
            "old_text": old_text,
            "new_text": new_text,
        },
    )


def _approve(action: ReplaceTextLiteralAction, request: ActionRequest) -> None:
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)


def test_preview_accepts_unique_literal_in_large_text_file(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_text("x" * 20000 + "\nTARGET=old\n", encoding="utf-8")
    adapter = WindowsFileSystemAdapter()

    evidence = adapter.preview_literal_text_replace(
        str(target),
        "TARGET=old",
        "TARGET=new",
    )

    assert evidence["allowed"] is True
    assert evidence["match_count"] == 1
    assert evidence["size_bytes"] > 16 * 1024
    assert evidence["preview_truncated"] is True
    assert evidence["preview_mode"] == "focused_literal"
    assert "-TARGET=old" in evidence["diff"]
    assert "+TARGET=new" in evidence["diff"]


def test_preview_rejects_missing_literal(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("alpha", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().preview_literal_text_replace(
        str(target),
        "missing",
        "new",
    )

    assert evidence["allowed"] is False
    assert evidence["error"] == "LITERAL_NOT_FOUND"
    assert evidence["match_count"] == 0


def test_preview_rejects_non_unique_literal(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("needle one needle two", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().preview_literal_text_replace(
        str(target),
        "needle",
        "replacement",
    )

    assert evidence["allowed"] is False
    assert evidence["error"] == "LITERAL_NOT_UNIQUE"
    assert evidence["match_count"] == 2


def test_replace_preserves_crlf_and_utf8_without_bom(tmp_path: Path) -> None:
    target = tmp_path / "windows.txt"
    target.write_bytes(b"alpha\r\nTARGET=old\r\nomega\r\n")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())
    request = _request(target, "TARGET=old", "TARGET=new")
    _approve(action, request)

    result = action.execute(request)

    assert result.success is True
    assert result.evidence["atomic_replace"] is True
    assert result.evidence["write_verified"] is True
    assert target.read_bytes() == b"alpha\r\nTARGET=new\r\nomega\r\n"
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_action_risk_and_code_preview_visibility(tmp_path: Path) -> None:
    text_target = tmp_path / "notes.txt"
    code_target = tmp_path / "module.py"
    text_target.write_text("old", encoding="utf-8")
    code_target.write_text("VALUE = 'old'\n", encoding="utf-8")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())

    assert action.risk_for(_request(text_target, "old", "new")) is ActionRisk.DESTRUCTIVE

    code_request = _request(code_target, "VALUE = 'old'", "VALUE = 'new'")
    assert action.risk_for(code_request) is ActionRisk.PRIVILEGED
    preview = action.confirmation_preview(code_request)
    assert preview.allowed is True
    assert "-VALUE = 'old'" in preview.text
    assert "+VALUE = 'new'" in preview.text


def test_sensitive_preview_redacts_literal_content(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    target.write_text("SECRET=old\n", encoding="utf-8")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())
    request = _request(target, "SECRET=old", "SECRET=new")

    assert action.risk_for(request) is ActionRisk.PRIVILEGED
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "SECRET=old" not in preview.text
    assert "SECRET=new" not in preview.text
    assert "ocultada" in preview.text


def test_execute_requires_local_preview_guard(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())

    result = action.execute(_request(target, "old", "new"))

    assert result.success is False
    assert result.error_code == "LITERAL_REPLACE_PREVIEW_REQUIRED"
    assert target.read_text(encoding="utf-8") == "old"


def test_execute_blocks_if_file_changes_after_preview(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())
    request = _request(target, "old", "new")
    _approve(action, request)
    target.write_text("changed elsewhere", encoding="utf-8")

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "FILE_CHANGED_AFTER_PREVIEW"
    assert target.read_text(encoding="utf-8") == "changed elsewhere"


def test_catalog_registers_strict_literal_replace_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["replace_text_literal"].parameters

    assert set(schema["properties"]) == {"path", "old_text", "new_text"}
    assert set(schema["required"]) == {"path", "old_text", "new_text"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["old_text"]["maxLength"] == 1024

    request = catalog.build_action_request(
        ToolCall(
            name="replace_text_literal",
            arguments={
                "path": r" C:\Temp\notes.txt ",
                "old_text": "before",
                "new_text": "after",
            },
        )
    )
    assert request.arguments == {
        "path": r"C:\Temp\notes.txt",
        "old_text": "before",
        "new_text": "after",
    }

    for old_text, new_text in (
        ("same", "same"),
        ("line\nbreak", "ok"),
        ("ok", "line\nbreak"),
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="replace_text_literal",
                    arguments={
                        "path": r"C:\Temp\notes.txt",
                        "old_text": old_text,
                        "new_text": new_text,
                    },
                )
            )


def test_bootstrap_registers_literal_replace_action() -> None:
    assert build_action_registry().contains("replace_text_literal") is True


class _ReplaceProvider:
    provider_id = "fake"

    def __init__(self, path: str) -> None:
        self.path = path

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="replace_text_literal",
                    arguments={
                        "path": self.path,
                        "old_text": "M69_OLD",
                        "new_text": "M69_NEW",
                    },
                    call_id="replace_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Substituição recebida.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_tool_gate_does_not_mutate_before_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "live.txt"
    target.write_text("before M69_OLD after", encoding="utf-8")
    action = ReplaceTextLiteralAction(WindowsFileSystemAdapter())
    registry = ActionRegistry()
    registry.register(
        action.name,
        action.execute,
        risk=action.risk_for,
        confirmation_preview=action.confirmation_preview,
    )
    catalog = build_default_tool_catalog()

    waiting = ToolLoopExecutor(
        _ReplaceProvider(str(target)),
        registry,
        catalog,
    ).execute(
        "Troque M69_OLD por M69_NEW.",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert target.read_text(encoding="utf-8") == "before M69_OLD after"


def test_literal_replace_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="replace_text_literal",
            arguments={
                "path": r"C:\Temp\notes.txt",
                "old_text": "old",
                "new_text": "new",
            },
        )
    )

    assert message == r"Substituindo texto literal em C:\Temp\notes.txt..."
