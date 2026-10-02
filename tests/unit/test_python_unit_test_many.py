from __future__ import annotations

from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.python_tests import RunPythonUnitTestFilesAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.python_tests import (
    MAX_PYTHON_UNIT_TEST_MANY_FILES,
    MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES,
    MIN_PYTHON_UNIT_TEST_MANY_FILES,
    WindowsPythonUnitTestAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    source = root / "src" / "theos"
    unit = root / "tests" / "unit"
    source.mkdir(parents=True)
    unit.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    return root, unit


def test_batch_catalog_has_strict_bounded_paths_schema() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_files"]
    schema = definition.parameters
    paths_schema = schema["properties"]["paths"]

    assert len(definitions) == 44
    assert set(schema["properties"]) == {"paths"}
    assert set(schema["required"]) == {"paths"}
    assert schema["additionalProperties"] is False
    assert paths_schema["minItems"] == 2
    assert paths_schema["maxItems"] == 4
    assert "uniqueItems" not in paths_schema

    request = catalog.build_action_request(
        ToolCall(
            name="run_python_unit_test_files",
            arguments={
                "paths": [
                    r" C:\Repo\tests\unit\test_a.py ",
                    r"C:\Repo\tests\unit\test_b.py",
                ]
            },
        )
    )
    assert request.arguments == {
        "paths": [
            r"C:\Repo\tests\unit\test_a.py",
            r"C:\Repo\tests\unit\test_b.py",
        ]
    }

    for invalid in (
        [r"C:\Repo\tests\unit\test_a.py"],
        [fr"C:\Repo\tests\unit\test_{i}.py" for i in range(5)],
        [
            r"C:\Repo\tests\unit\test_a.py",
            r"c:\repo\tests\unit\TEST_A.PY",
        ],
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="run_python_unit_test_files",
                    arguments={"paths": invalid},
                )
            )


def test_batch_preview_hashes_explicit_targets_once(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    first = unit / "test_a.py"
    second = unit / "test_b.py"
    first.write_text("def test_a():\n    assert True\n", encoding="utf-8")
    second.write_text("def test_b():\n    assert True\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_targets(
        [str(first), str(second)]
    )

    assert "error" not in evidence
    assert evidence["selected_file_count"] == 2
    assert evidence["selected_total_bytes"] > 0
    assert len(evidence["targets"]) == 2
    assert [item["path"] for item in evidence["targets"]] == [
        str(first.resolve()),
        str(second.resolve()),
    ]
    assert all(len(str(item["sha256"])) == 64 for item in evidence["targets"])
    assert len(str(evidence["project_python_manifest_sha256"])) == 64
    assert evidence["source_content_returned"] is False


def test_batch_preview_rejects_duplicate_resolved_target(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_dup.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_targets(
        [str(target), str(target)]
    )

    assert evidence["error"] == "DUPLICATE_RESOLVED_TARGET"
    assert evidence["error_target_index"] == 1


def test_batch_preview_rejects_file_count_out_of_range(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_one.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_targets(
        [str(target)]
    )

    assert evidence["error"] == "TEST_BATCH_FILE_COUNT_OUT_OF_RANGE"


def test_batch_preview_rejects_total_bytes_limit(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    paths: list[str] = []
    payload = b"#" * (200 * 1024)
    for index in range(4):
        target = unit / f"test_large_{index}.py"
        target.write_bytes(payload)
        paths.append(str(target))

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_targets(paths)

    assert evidence["selected_total_bytes"] > MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES
    assert evidence["error"] == "TEST_BATCH_TOTAL_BYTES_TOO_LARGE"


class _PreviewAdapter:
    def preview_test_targets(self, raw_paths):
        assert raw_paths == [r"C:\Repo\tests\unit\test_a.py", r"C:\Repo\tests\unit\test_b.py"]
        return {
            "targets": [
                {
                    "path": raw_paths[0],
                    "sha256": "a" * 64,
                    "size_bytes": 100,
                },
                {
                    "path": raw_paths[1],
                    "sha256": "b" * 64,
                    "size_bytes": 200,
                },
            ],
            "selected_file_count": 2,
            "selected_total_bytes": 300,
            "project_python_manifest_sha256": "c" * 64,
        }

    @staticmethod
    def preview_pytest_verifier():
        return {
            "pytest_verifier_path": r"C:\Repo\.venv\Scripts\pytest.exe",
            "pytest_verifier_sha256": "d" * 64,
        }

    @staticmethod
    def preview_pytest_package_state():
        return {"pytest_package_manifest_sha256": "e" * 64}

    @staticmethod
    def preview_python_runtime_state():
        return {"python_runtime_state_sha256": "f" * 64}


def test_batch_action_preview_binds_every_explicit_target() -> None:
    action = RunPythonUnitTestFilesAction(_PreviewAdapter())
    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_files",
            arguments={
                "paths": [
                    r"C:\Repo\tests\unit\test_a.py",
                    r"C:\Repo\tests\unit\test_b.py",
                ]
            },
        )
    )

    assert preview.allowed is True
    assert preview.execution_guard["_expected_test_batch_targets"] == [
        {
            "path": r"C:\Repo\tests\unit\test_a.py",
            "sha256": "a" * 64,
        },
        {
            "path": r"C:\Repo\tests\unit\test_b.py",
            "sha256": "b" * 64,
        },
    ]
    assert "máximo de 4 subprocessos pytest" in preview.text
    assert "Não há diretório, glob, node selector" in preview.text
    assert RunPythonUnitTestFilesAction.risk is ActionRisk.PRIVILEGED


class _ExecuteAdapter:
    def __init__(self, results):
        self.results = list(results)
        self.calls: list[str] = []

    @staticmethod
    def preview_test_targets(raw_paths):
        return {
            "targets": [
                {
                    "path": path,
                    "sha256": chr(ord("a") + index) * 64,
                    "size_bytes": 100,
                }
                for index, path in enumerate(raw_paths)
            ],
            "selected_file_count": len(raw_paths),
            "selected_total_bytes": 100 * len(raw_paths),
            "project_python_manifest_sha256": "c" * 64,
        }

    def run_test_file(self, raw_path, **kwargs):
        _ = kwargs
        self.calls.append(raw_path)
        return self.results[len(self.calls) - 1]


def _approved_batch_request(paths: list[str]) -> ActionRequest:
    return ActionRequest(
        action="run_python_unit_test_files",
        arguments={
            "paths": paths,
            "_expected_test_batch_targets": [
                {
                    "path": path,
                    "sha256": chr(ord("a") + index) * 64,
                }
                for index, path in enumerate(paths)
            ],
            "_expected_project_python_manifest_sha256": "c" * 64,
            "_expected_pytest_verifier_path": r"C:\Repo\.venv\Scripts\pytest.exe",
            "_expected_pytest_verifier_sha256": "d" * 64,
            "_expected_pytest_package_manifest_sha256": "e" * 64,
            "_expected_python_runtime_state_sha256": "f" * 64,
        },
    )


def _passing_result(tests: int = 1) -> dict[str, object]:
    return {
        "tests_run": tests,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "passed": True,
        "no_tests_collected": False,
        "failure_diagnostic_total": 0,
        "failure_diagnostics": [],
        "test_code_executed": True,
    }


def test_batch_execute_composes_single_file_runner_in_order() -> None:
    paths = [
        r"C:\Repo\tests\unit\test_a.py",
        r"C:\Repo\tests\unit\test_b.py",
    ]
    adapter = _ExecuteAdapter([_passing_result(2), _passing_result(3)])
    result = RunPythonUnitTestFilesAction(adapter).execute(
        _approved_batch_request(paths)
    )

    assert result.success is True
    assert adapter.calls == paths
    assert result.evidence["batch_files_processed"] == 2
    assert result.evidence["pytest_processes_started"] == 2
    assert result.evidence["tests_run"] == 5
    assert result.evidence["all_passed"] is True
    assert result.evidence["max_pytest_processes"] == 4
    assert result.evidence["project_wide_test_authority"] is False


def test_batch_caps_failure_diagnostics_globally() -> None:
    paths = [
        r"C:\Repo\tests\unit\test_a.py",
        r"C:\Repo\tests\unit\test_b.py",
    ]
    first = {
        **_passing_result(),
        "passed": False,
        "failures": 2,
        "failure_diagnostic_total": 2,
        "failure_diagnostics": [
            {"kind": "failure", "test_name": "a1", "class_name": "A", "message": "x"},
            {"kind": "failure", "test_name": "a2", "class_name": "A", "message": "y"},
        ],
    }
    second = {
        **_passing_result(),
        "passed": False,
        "failures": 2,
        "failure_diagnostic_total": 2,
        "failure_diagnostics": [
            {"kind": "failure", "test_name": "b1", "class_name": "B", "message": "z"},
            {"kind": "failure", "test_name": "b2", "class_name": "B", "message": "w"},
        ],
    }

    result = RunPythonUnitTestFilesAction(
        _ExecuteAdapter([first, second])
    ).execute(_approved_batch_request(paths))

    assert result.success is True
    assert result.evidence["failure_diagnostic_total"] == 4
    assert len(result.evidence["failure_diagnostics"]) == 3
    assert result.evidence["failure_diagnostics_truncated"] is True
    assert result.evidence["all_passed"] is False


def test_batch_stops_remaining_files_on_operational_guard_error() -> None:
    paths = [
        r"C:\Repo\tests\unit\test_a.py",
        r"C:\Repo\tests\unit\test_b.py",
        r"C:\Repo\tests\unit\test_c.py",
    ]
    adapter = _ExecuteAdapter(
        [
            _passing_result(),
            {"error": "PYTEST_VERIFIER_CHANGED_AFTER_PREVIEW"},
            _passing_result(),
        ]
    )

    result = RunPythonUnitTestFilesAction(adapter).execute(
        _approved_batch_request(paths)
    )

    assert result.success is False
    assert result.error_code == "PYTEST_VERIFIER_CHANGED_AFTER_PREVIEW"
    assert adapter.calls == paths[:2]
    assert result.evidence["error_target_index"] == 1
    assert result.evidence["batch_files_processed"] == 2
    assert result.evidence["pytest_processes_started"] == 1


def test_bootstrap_registers_python_unit_test_files_action() -> None:
    registry = build_action_registry()
    assert registry.contains("run_python_unit_test_files") is True


class _BatchProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="run_python_unit_test_files",
                    arguments={
                        "paths": [
                            r"C:\Repo\tests\unit\test_a.py",
                            r"C:\Repo\tests\unit\test_b.py",
                        ]
                    },
                    call_id="batch_tests_1",
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


def test_batch_gate_does_not_execute_before_confirmation() -> None:
    executed: list[list[str]] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        paths = request.arguments["paths"]
        assert isinstance(paths, list)
        executed.append(list(paths))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Batch concluído.",
        )

    registry.register(
        RunPythonUnitTestFilesAction.name,
        handler,
        risk=RunPythonUnitTestFilesAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="batch",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _BatchProvider(),
        registry,
        catalog,
    ).execute(
        "Execute esses dois testes.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_python_unit_test_files_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="run_python_unit_test_files",
            arguments={
                "paths": [
                    r"C:\Repo\tests\unit\test_a.py",
                    r"C:\Repo\tests\unit\test_b.py",
                ]
            },
        )
    )

    assert message == "Executando lote de 2 arquivos de teste Python..."


def test_batch_constants_are_narrow() -> None:
    assert MIN_PYTHON_UNIT_TEST_MANY_FILES == 2
    assert MAX_PYTHON_UNIT_TEST_MANY_FILES == 4
    assert MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES == 768 * 1024
