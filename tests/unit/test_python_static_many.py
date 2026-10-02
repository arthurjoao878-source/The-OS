from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.file_system import CheckPythonStaticManyAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import (
    MAX_PYTHON_STATIC_FILE_BYTES,
    MAX_PYTHON_STATIC_MANY_TOTAL_BYTES,
    WindowsFileSystemAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_static_many_clean_runtime_traps_do_not_execute_or_mutate(
    tmp_path: Path,
) -> None:
    sentinel_a = tmp_path / "executed-a.txt"
    sentinel_b = tmp_path / "executed-b.txt"
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text(
        "from pathlib import Path\n\n"
        f"Path({str(sentinel_a)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    second.write_text(
        "from pathlib import Path\n\n"
        f"Path({str(sentinel_b)!r}).write_text('executed', encoding='utf-8')\n"
        'raise RuntimeError("M73_MUST_NOT_EXECUTE")\n',
        encoding="utf-8",
    )
    before = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (first, second)
    }

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(second)]
    )

    assert evidence["lint_clean"] is True
    assert evidence["files_count"] == 2
    assert evidence["all_targets_unchanged"] is True
    assert evidence["target_modified"] is False
    assert evidence["target_code_executed"] is False
    assert evidence["target_imported"] is False
    assert evidence["shell_used"] is False
    assert evidence["ruff_fix_enabled"] is False
    assert evidence["ruff_cache_enabled"] is False
    for target in evidence["targets"]:
        assert target["before_sha256"] == target["after_sha256"]
        assert target["target_unchanged"] is True
        assert target["before_sha256"] == before[target["path"]]
    assert sentinel_a.exists() is False
    assert sentinel_b.exists() is False
    assert (tmp_path / ".ruff_cache").exists() is False
    assert (tmp_path / "__pycache__").exists() is False


def test_static_many_maps_diagnostics_to_explicit_targets(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("print(M73_FIRST_UNDEFINED)\n", encoding="utf-8")
    second.write_text("print(M73_SECOND_UNDEFINED)\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(second)]
    )

    assert evidence["lint_clean"] is False
    assert evidence["total_diagnostics"] == 2
    by_code = [item for item in evidence["diagnostics"] if item["code"] == "F821"]
    assert len(by_code) == 2
    assert {item["path"] for item in by_code} == {
        str(first.resolve()),
        str(second.resolve()),
    }
    assert any("M73_FIRST_UNDEFINED" in item["message"] for item in by_code)
    assert any("M73_SECOND_UNDEFINED" in item["message"] for item in by_code)
    assert all("source" not in item for item in by_code)


def test_static_many_caps_global_diagnostics(tmp_path: Path) -> None:
    first = tmp_path / "many_a.py"
    second = tmp_path / "many_b.py"
    first.write_text(
        "".join(f"print(M73_A_{index})\n" for index in range(25)),
        encoding="utf-8",
    )
    second.write_text(
        "".join(f"print(M73_B_{index})\n" for index in range(25)),
        encoding="utf-8",
    )

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(second)]
    )

    assert evidence["total_diagnostics"] >= 50
    assert len(evidence["diagnostics"]) == 40
    assert evidence["diagnostics_truncated"] is True


def test_static_many_rejects_duplicate_resolved_target(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    alias = target.parent / "missing-dir" / ".." / target.name

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(target), str(alias)]
    )

    assert evidence["error"] == "DUPLICATE_RESOLVED_TARGET"
    assert "verifier_exit_code" not in evidence


def test_static_many_catalog_has_strict_bounded_paths_schema() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["check_python_static_many"].parameters
    paths_schema = schema["properties"]["paths"]

    assert set(schema["properties"]) == {"paths"}
    assert set(schema["required"]) == {"paths"}
    assert schema["additionalProperties"] is False
    assert paths_schema["minItems"] == 2
    assert paths_schema["maxItems"] == 8
    assert "uniqueItems" not in paths_schema

    request = catalog.build_action_request(
        ToolCall(
            name="check_python_static_many",
            arguments={
                "paths": [
                    r" C:\Temp\a.py ",
                    r"C:\Temp\b.py",
                ]
            },
        )
    )
    assert request.arguments == {
        "paths": [r"C:\Temp\a.py", r"C:\Temp\b.py"]
    }

    for invalid_paths in (
        [r"C:\Temp\a.py"],
        [fr"C:\Temp\{index}.py" for index in range(9)],
        [r"C:\Temp\a.py", r"c:\temp\A.PY"],
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="check_python_static_many",
                    arguments={"paths": invalid_paths},
                )
            )


def test_static_many_rejects_non_python_target_before_verifier(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "notes.txt"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_text("value = 2\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(second)]
    )

    assert evidence["error"] == "PYTHON_SOURCE_SUFFIX_REQUIRED"
    assert evidence["error_target_index"] == 1
    assert "verifier_exit_code" not in evidence


def test_static_many_rejects_oversized_single_target(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "large.py"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_bytes(b"#" * (MAX_PYTHON_STATIC_FILE_BYTES + 1))

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(second)]
    )

    assert evidence["error"] == "FILE_TOO_LARGE"
    assert evidence["error_target_index"] == 1
    assert "verifier_exit_code" not in evidence


def test_static_many_rejects_total_bytes_before_verifier(tmp_path: Path) -> None:
    paths: list[str] = []
    payload = b"#" * (220 * 1024)
    for index in range(5):
        target = tmp_path / f"large_{index}.py"
        target.write_bytes(payload)
        paths.append(str(target))

    evidence = WindowsFileSystemAdapter().check_python_static_many(paths)

    assert evidence["total_bytes"] > MAX_PYTHON_STATIC_MANY_TOTAL_BYTES
    assert evidence["error"] == "TOTAL_BYTES_TOO_LARGE"
    assert "verifier_exit_code" not in evidence
    assert all("before_sha256" not in target for target in evidence["targets"])


def test_static_many_reports_missing_target_before_verifier(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    missing = tmp_path / "missing.py"
    first.write_text("value = 1\n", encoding="utf-8")

    evidence = WindowsFileSystemAdapter().check_python_static_many(
        [str(first), str(missing)]
    )

    assert evidence["error"] == "TARGET_NOT_FOUND"
    assert evidence["error_target_index"] == 1
    assert "verifier_exit_code" not in evidence


def test_bootstrap_registers_python_static_many_action() -> None:
    assert build_action_registry().contains("check_python_static_many") is True


class _StaticManyProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="check_python_static_many",
                    arguments={
                        "paths": [
                            r"C:\Temp\a.py",
                            r"C:\Temp\b.py",
                        ]
                    },
                    call_id="static_many_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Batch recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_static_many_gate_does_not_start_verifier_before_confirmation() -> None:
    executed: list[list[str]] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        raw_paths = request.arguments["paths"]
        assert isinstance(raw_paths, list)
        executed.append(list(raw_paths))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Batch concluído.",
            evidence={"lint_clean": True},
        )

    registry.register(
        CheckPythonStaticManyAction.name,
        handler,
        risk=CheckPythonStaticManyAction.risk,
        confirmation_preview=lambda request: (
            CheckPythonStaticManyAction(WindowsFileSystemAdapter())
            .confirmation_preview(request)
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _StaticManyProvider(),
        registry,
        catalog,
    ).execute(
        "Analise os dois arquivos.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_python_static_many_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="check_python_static_many",
            arguments={
                "paths": [r"C:\Temp\a.py", r"C:\Temp\b.py"],
            },
        )
    )

    assert message == "Analisando estaticamente 2 arquivos Python..."
