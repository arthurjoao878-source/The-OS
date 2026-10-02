from __future__ import annotations

from pathlib import Path

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.file_system import CheckPythonSyntaxAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import (
    MAX_PYTHON_SYNTAX_FILE_BYTES,
    WindowsFileSystemAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_syntax_check_validates_without_executing_source(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    target = tmp_path / "compile_only.py"
    target.write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        "raise RuntimeError('M71_MUST_NOT_EXECUTE')\n",
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().check_python_syntax(str(target))

    assert evidence["syntax_valid"] is True
    assert evidence["code_executed"] is False
    assert evidence["imports_executed"] is False
    assert evidence["bytecode_written"] is False
    assert evidence["source_content_returned"] is False
    assert sentinel.exists() is False
    assert (tmp_path / "__pycache__").exists() is False


def test_syntax_check_reports_error_without_source_text(tmp_path: Path) -> None:
    target = tmp_path / "invalid.py"
    secret_line = "SECRET_SOURCE_LINE = 'SHOULD_NOT_RETURN'"
    target.write_text(
        "if True print('broken')\n" + secret_line + "\n",
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().check_python_syntax(str(target))

    assert evidence["syntax_valid"] is False
    assert evidence["diagnostic_code"] == "PYTHON_SYNTAX_ERROR"
    assert evidence["diagnostic_line"] == 1
    assert evidence["diagnostic_is_untrusted_data"] is True
    assert "content" not in evidence
    assert "source" not in evidence
    assert secret_line not in str(evidence)


def test_syntax_check_respects_python_encoding_cookie(tmp_path: Path) -> None:
    target = tmp_path / "latin1.py"
    target.write_bytes(
        b"# -*- coding: latin-1 -*-\n"
        b"name = 'caf\xe9'\n"
    )

    evidence = WindowsFileSystemAdapter().check_python_syntax(str(target))

    assert evidence["syntax_valid"] is True
    assert evidence["encoding"].casefold() in {
        "iso-8859-1",
        "latin-1",
    }


def test_syntax_check_rejects_non_python_suffix(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("value = 1\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_syntax(str(target))

    assert evidence["error"] == "PYTHON_SOURCE_SUFFIX_REQUIRED"
    assert "syntax_valid" not in evidence


class _LinkLikeAdapter(WindowsFileSystemAdapter):
    @staticmethod
    def _is_link_like(path: Path) -> bool:
        _ = path
        return True


def test_syntax_check_rejects_link_like_target(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")

    evidence = _LinkLikeAdapter().check_python_syntax(str(target))

    assert evidence["error"] == "LINK_TARGET_NOT_ALLOWED"
    assert "syntax_valid" not in evidence


def test_syntax_check_rejects_oversized_file(tmp_path: Path) -> None:
    target = tmp_path / "large.py"
    target.write_bytes(b"#" * (MAX_PYTHON_SYNTAX_FILE_BYTES + 1))

    evidence = WindowsFileSystemAdapter().check_python_syntax(str(target))

    assert evidence["error"] == "FILE_TOO_LARGE"
    assert evidence["size_bytes"] == MAX_PYTHON_SYNTAX_FILE_BYTES + 1
    assert "bytes_read" not in evidence


def test_action_treats_invalid_syntax_as_verified_diagnostic(
    tmp_path: Path,
) -> None:
    target = tmp_path / "invalid.py"
    target.write_text("def broken(:\n    pass\n", encoding="utf-8")
    action = CheckPythonSyntaxAction(WindowsFileSystemAdapter())

    result = action.execute(
        ActionRequest(
            action="check_python_syntax",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["syntax_valid"] is False
    assert result.evidence["diagnostic_code"] == "PYTHON_SYNTAX_ERROR"


def test_catalog_registers_strict_python_syntax_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["check_python_syntax"].parameters

    assert set(schema["properties"]) == {"path"}
    assert set(schema["required"]) == {"path"}
    assert schema["additionalProperties"] is False

    request = catalog.build_action_request(
        ToolCall(
            name="check_python_syntax",
            arguments={"path": r" C:\Temp\module.py "},
        )
    )
    assert request.arguments == {"path": r"C:\Temp\module.py"}


def test_bootstrap_registers_python_syntax_action() -> None:
    assert build_action_registry().contains("check_python_syntax") is True


class _SyntaxProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="check_python_syntax",
                    arguments={"path": r"C:\Temp\module.py"},
                    call_id="syntax_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Sintaxe recebida.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_tool_gate_does_not_read_before_confirmation() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(str(request.arguments["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Sintaxe verificada.",
            evidence={"syntax_valid": True},
        )

    registry.register(
        CheckPythonSyntaxAction.name,
        handler,
        risk=CheckPythonSyntaxAction.risk,
        confirmation_preview=lambda request: (
            CheckPythonSyntaxAction(WindowsFileSystemAdapter())
            .confirmation_preview(request)
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _SyntaxProvider(),
        registry,
        catalog,
    ).execute(
        "Verifique a sintaxe.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_python_syntax_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="check_python_syntax",
            arguments={"path": r"C:\Temp\module.py"},
        )
    )

    assert message == r"Verificando sintaxe Python em C:\Temp\module.py..."
