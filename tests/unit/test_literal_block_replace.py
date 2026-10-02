from __future__ import annotations

from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import ReplaceTextBlockAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.lyra.execution import ToolLoopExecutor


def _request(path: Path, old_block: str, new_block: str) -> ActionRequest:
    return ActionRequest(
        action="replace_text_block",
        arguments={
            "path": str(path),
            "old_block": old_block,
            "new_block": new_block,
        },
    )


def _approve(action: ReplaceTextBlockAction, request: ActionRequest) -> None:
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)


def test_block_replace_matches_lf_proposal_against_crlf_and_preserves_crlf(
    tmp_path: Path,
) -> None:
    target = tmp_path / "windows.txt"
    target.write_bytes(b"head\r\nalpha\r\nbeta\r\ntail\r\n")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())
    request = _request(
        target,
        "alpha\nbeta",
        "alpha\nBETA\nadded",
    )

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Newline aplicado ao bloco novo: CRLF" in preview.text
    request.arguments.update(preview.execution_guard)

    result = action.execute(request)

    assert result.success is True
    assert result.evidence["newline_style"] == "CRLF"
    assert result.evidence["atomic_replace"] is True
    assert result.evidence["write_verified"] is True
    assert target.read_bytes() == b"head\r\nalpha\r\nBETA\r\nadded\r\ntail\r\n"


def test_block_preview_rejects_missing_block(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().preview_literal_block_replace(
        str(target),
        "missing\nblock",
        "replacement",
    )

    assert evidence["allowed"] is False
    assert evidence["error"] == "LITERAL_BLOCK_NOT_FOUND"
    assert evidence["match_count"] == 0


def test_block_preview_rejects_non_unique_after_newline_normalization(
    tmp_path: Path,
) -> None:
    target = tmp_path / "mixed.txt"
    target.write_bytes(b"alpha\r\nbeta\r\nmiddle\nalpha\nbeta\n")

    evidence = WindowsFileSystemAdapter().preview_literal_block_replace(
        str(target),
        "alpha\nbeta",
        "replacement",
    )

    assert evidence["allowed"] is False
    assert evidence["error"] == "LITERAL_BLOCK_NOT_UNIQUE"
    assert evidence["match_count"] == 2


def test_block_preview_fallback_keeps_complete_changed_blocks_visible(
    tmp_path: Path,
) -> None:
    target = tmp_path / "large.txt"
    target.write_text(
        "x" * 20000 + "\nold one\nold two\ntail\n",
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().preview_literal_block_replace(
        str(target),
        "old one\nold two",
        "new one\nnew two\nnew three",
    )

    assert evidence["allowed"] is True
    assert evidence["preview_truncated"] is True
    assert evidence["preview_mode"] == "focused_block"
    assert "-old one\n-old two\n" in evidence["diff"]
    assert "+new one\n+new two\n+new three\n" in evidence["diff"]


def test_block_action_risk_and_credential_preview(tmp_path: Path) -> None:
    text_target = tmp_path / "notes.txt"
    code_target = tmp_path / "module.py"
    secret_target = tmp_path / ".env"
    text_target.write_text("a\nb\n", encoding="utf-8")
    code_target.write_text("a\nb\n", encoding="utf-8")
    secret_target.write_text("SECRET=old\nVALUE=1\n", encoding="utf-8")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())

    assert action.risk_for(_request(text_target, "a\nb", "c\nd")) is ActionRisk.DESTRUCTIVE
    assert action.risk_for(_request(code_target, "a\nb", "c\nd")) is ActionRisk.PRIVILEGED

    secret_request = _request(
        secret_target,
        "SECRET=old\nVALUE=1",
        "SECRET=new\nVALUE=2",
    )
    assert action.risk_for(secret_request) is ActionRisk.PRIVILEGED
    preview = action.confirmation_preview(secret_request)
    assert preview.allowed is True
    assert "SECRET=old" not in preview.text
    assert "SECRET=new" not in preview.text
    assert "ocultada" in preview.text


def test_block_execute_requires_preview_guard(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old\nblock\n", encoding="utf-8")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())

    result = action.execute(_request(target, "old\nblock", "new\nblock"))

    assert result.success is False
    assert result.error_code == "LITERAL_BLOCK_PREVIEW_REQUIRED"
    assert target.read_text(encoding="utf-8") == "old\nblock\n"


def test_block_execute_blocks_if_file_changes_after_preview(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old\nblock\n", encoding="utf-8")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())
    request = _request(target, "old\nblock", "new\nblock")
    _approve(action, request)
    target.write_text("changed elsewhere\n", encoding="utf-8")

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "FILE_CHANGED_AFTER_PREVIEW"
    assert target.read_text(encoding="utf-8") == "changed elsewhere\n"


def test_block_execute_blocks_if_proposal_changes_after_preview(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old\nblock\n", encoding="utf-8")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())
    request = _request(target, "old\nblock", "new\nblock")
    _approve(action, request)
    request.arguments["new_block"] = "tampered\nblock"

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "BLOCK_CHANGED_AFTER_PREVIEW"
    assert target.read_text(encoding="utf-8") == "old\nblock\n"


def test_catalog_registers_strict_multiline_block_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["replace_text_block"].parameters

    assert set(schema["properties"]) == {"path", "old_block", "new_block"}
    assert set(schema["required"]) == {"path", "old_block", "new_block"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["old_block"]["maxLength"] == 1024

    request = catalog.build_action_request(
        ToolCall(
            name="replace_text_block",
            arguments={
                "path": r" C:\Temp\notes.txt ",
                "old_block": "alpha\nbeta",
                "new_block": "alpha\nBETA\ngamma",
            },
        )
    )
    assert request.arguments == {
        "path": r"C:\Temp\notes.txt",
        "old_block": "alpha\nbeta",
        "new_block": "alpha\nBETA\ngamma",
    }


def test_catalog_rejects_block_limits_nul_and_newline_only_noop() -> None:
    catalog = build_default_tool_catalog()
    invalid_pairs = (
        ("same\r\nblock", "same\nblock"),
        ("ok\0bad", "new"),
        ("old", "new\0bad"),
        ("\n".join(["x"] * 41), "new"),
        ("old", "\n".join(["x"] * 41)),
        ("x" * 1025, "new"),
        ("old", "x" * 1025),
    )

    for old_block, new_block in invalid_pairs:
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="replace_text_block",
                    arguments={
                        "path": r"C:\Temp\notes.txt",
                        "old_block": old_block,
                        "new_block": new_block,
                    },
                )
            )


def test_bootstrap_registers_literal_block_replace_action() -> None:
    assert build_action_registry().contains("replace_text_block") is True


class _BlockProvider:
    provider_id = "fake"

    def __init__(self, path: str) -> None:
        self.path = path

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="replace_text_block",
                    arguments={
                        "path": self.path,
                        "old_block": "M70_OLD_A\nM70_OLD_B",
                        "new_block": "M70_NEW_A\nM70_NEW_B",
                    },
                    call_id="block_replace_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Bloco recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_block_tool_gate_and_progress_are_bounded(tmp_path: Path) -> None:
    target = tmp_path / "live.txt"
    target.write_text("M70_OLD_A\nM70_OLD_B\n", encoding="utf-8")
    action = ReplaceTextBlockAction(WindowsFileSystemAdapter())
    registry = ActionRegistry()
    registry.register(
        action.name,
        action.execute,
        risk=action.risk_for,
        confirmation_preview=action.confirmation_preview,
    )
    catalog = build_default_tool_catalog()

    waiting = ToolLoopExecutor(
        _BlockProvider(str(target)),
        registry,
        catalog,
    ).execute(
        "Substitua o bloco.",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert target.read_text(encoding="utf-8") == "M70_OLD_A\nM70_OLD_B\n"

    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="replace_text_block",
            arguments={
                "path": r"C:\Temp\notes.txt",
                "old_block": "a\nb",
                "new_block": "c\nd",
            },
        )
    )
    assert message == r"Substituindo bloco literal em C:\Temp\notes.txt..."
