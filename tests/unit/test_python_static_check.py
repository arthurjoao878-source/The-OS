from __future__ import annotations

import hashlib
from pathlib import Path

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.file_system import CheckPythonStaticAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import (
    MAX_PYTHON_STATIC_FILE_BYTES,
    WindowsFileSystemAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_static_check_clean_runtime_trap_does_not_execute_or_mutate(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    target = tmp_path / "runtime_trap.py"
    target.write_text(
        "from pathlib import Path\n\n"
        f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n"
        'raise RuntimeError("M72_MUST_NOT_EXECUTE")\n',
        encoding="utf-8",
    )
    before = target.read_bytes()
    before_sha = hashlib.sha256(before).hexdigest()

    evidence = WindowsFileSystemAdapter().check_python_static(str(target))

    assert evidence["lint_clean"] is True
    assert evidence["total_diagnostics"] == 0
    assert evidence["target_code_executed"] is False
    assert evidence["target_imported"] is False
    assert evidence["target_modified"] is False
    assert evidence["target_unchanged"] is True
    assert evidence["before_sha256"] == before_sha
    assert evidence["after_sha256"] == before_sha
    assert evidence["shell_used"] is False
    assert evidence["ruff_fix_enabled"] is False
    assert evidence["ruff_cache_enabled"] is False
    assert evidence["isolated_mode"] is True
    assert evidence["source_content_returned"] is False
    assert sentinel.exists() is False
    assert target.read_bytes() == before
    assert (tmp_path / ".ruff_cache").exists() is False
    assert (tmp_path / "__pycache__").exists() is False


def test_static_check_returns_structured_f821_without_source_line(
    tmp_path: Path,
) -> None:
    target = tmp_path / "invalid_name.py"
    source_line = "print(M72_UNDEFINED_NAME)"
    target.write_text(source_line + "\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_static(str(target))

    assert evidence["lint_clean"] is False
    assert evidence["total_diagnostics"] >= 1
    diagnostic = next(
        item for item in evidence["diagnostics"] if item["code"] == "F821"
    )
    assert diagnostic["line"] == 1
    assert diagnostic["column"] >= 1
    assert "M72_UNDEFINED_NAME" in diagnostic["message"]
    assert "source" not in diagnostic
    assert "filename" not in diagnostic
    assert source_line not in str(diagnostic)
    assert evidence["diagnostic_is_untrusted_data"] is True


def test_static_check_caps_provider_visible_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "many.py"
    target.write_text(
        "".join(f"print(M72_UNDEFINED_{index})\n" for index in range(30)),
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().check_python_static(str(target))

    assert evidence["total_diagnostics"] >= 20
    assert len(evidence["diagnostics"]) == 20
    assert evidence["diagnostics_truncated"] is True


def test_static_check_rejects_non_python_suffix(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("value = 1\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_static(str(target))

    assert evidence["error"] == "PYTHON_SOURCE_SUFFIX_REQUIRED"
    assert "verifier_exit_code" not in evidence


class _LinkLikeAdapter(WindowsFileSystemAdapter):
    @staticmethod
    def _is_link_like(path: Path) -> bool:
        _ = path
        return True


def test_static_check_rejects_link_like_target(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")

    evidence = _LinkLikeAdapter().check_python_static(str(target))

    assert evidence["error"] == "LINK_TARGET_NOT_ALLOWED"
    assert "before_sha256" not in evidence


def test_static_check_rejects_oversized_file(tmp_path: Path) -> None:
    target = tmp_path / "large.py"
    target.write_bytes(b"#" * (MAX_PYTHON_STATIC_FILE_BYTES + 1))

    evidence = WindowsFileSystemAdapter().check_python_static(str(target))

    assert evidence["error"] == "FILE_TOO_LARGE"
    assert evidence["size_bytes"] == MAX_PYTHON_STATIC_FILE_BYTES + 1
    assert "before_sha256" not in evidence


def test_action_treats_lint_diagnostics_as_verified_result(tmp_path: Path) -> None:
    target = tmp_path / "diagnostic.py"
    target.write_text("print(M72_MISSING)\n", encoding="utf-8")
    action = CheckPythonStaticAction(WindowsFileSystemAdapter())

    result = action.execute(
        ActionRequest(
            action="check_python_static",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["lint_clean"] is False
    assert result.evidence["total_diagnostics"] >= 1


def test_catalog_registers_strict_python_static_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["check_python_static"].parameters

    assert set(schema["properties"]) == {"path"}
    assert set(schema["required"]) == {"path"}
    assert schema["additionalProperties"] is False

    request = catalog.build_action_request(
        ToolCall(
            name="check_python_static",
            arguments={"path": r" C:\Temp\module.py "},
        )
    )
    assert request.arguments == {"path": r"C:\Temp\module.py"}


def test_bootstrap_registers_python_static_action() -> None:
    assert build_action_registry().contains("check_python_static") is True


class _StaticProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="check_python_static",
                    arguments={"path": r"C:\Temp\module.py"},
                    call_id="static_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Análise recebida.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_static_tool_gate_does_not_start_verifier_before_confirmation() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(str(request.arguments["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Análise concluída.",
            evidence={"lint_clean": True},
        )

    registry.register(
        CheckPythonStaticAction.name,
        handler,
        risk=CheckPythonStaticAction.risk,
        confirmation_preview=lambda request: (
            CheckPythonStaticAction(WindowsFileSystemAdapter())
            .confirmation_preview(request)
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _StaticProvider(),
        registry,
        catalog,
    ).execute(
        "Analise estaticamente.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_python_static_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="check_python_static",
            arguments={"path": r"C:\Temp\module.py"},
        )
    )

    assert message == r"Analisando Python estaticamente em C:\Temp\module.py..."
