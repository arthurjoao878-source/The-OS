from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.python_tests import RunPythonUnitTestFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.python_tests import WindowsPythonUnitTestAdapter
from theos.lyra.execution import ToolLoopExecutor


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    unit = root / "tests" / "unit"
    source = root / "src" / "theos"
    unit.mkdir(parents=True)
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    return root, unit


def _write_junit(command: list[str], *, tests: int, failures: int, errors: int = 0) -> None:
    report_arg = next(item for item in command if item.startswith("--junitxml="))
    report = Path(report_arg.split("=", 1)[1])
    report.write_text(
        (
            '<testsuites><testsuite '
            f'tests="{tests}" failures="{failures}" errors="{errors}" skipped="0">'
            "</testsuite></testsuites>"
        ),
        encoding="utf-8",
    )


def test_preview_hashes_exact_explicit_unit_test(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_sample.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    adapter = WindowsPythonUnitTestAdapter(root)

    evidence = adapter.preview_test_target(str(target))

    assert evidence["path"] == str(target.resolve())
    assert evidence["bytes_hashed"] == target.stat().st_size
    assert len(str(evidence["sha256"])) == 64
    assert evidence["hash_only_preflight"] is True
    assert evidence["source_content_returned"] is False
    assert evidence["test_code_executed"] is False
    assert evidence["sandboxed"] is False


def test_preview_rejects_target_outside_tests_unit(tmp_path: Path) -> None:
    root, _ = _project(tmp_path)
    target = root / "test_outside.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_target(str(target))

    assert evidence["error"] == "TEST_TARGET_OUTSIDE_UNIT_ROOT"
    assert "sha256" not in evidence


def test_preview_rejects_non_test_filename(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "helper.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_target(str(target))

    assert evidence["error"] == "UNIT_TEST_FILE_REQUIRED"
    assert "sha256" not in evidence


def test_action_is_privileged_and_preview_binds_hash(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_bound.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))

    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert action.risk is ActionRisk.PRIVILEGED
    assert preview.allowed is True
    assert preview.execution_guard["_expected_test_path"] == str(target.resolve())
    assert len(preview.execution_guard["_expected_test_sha256"]) == 64
    assert "NÃO fornece sandbox" in preview.text


def test_run_uses_fixed_pytest_policy_and_parses_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_pass.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        _write_junit(list(command), tests=1, failures=0)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    command = captured["command"]
    kwargs = captured["kwargs"]
    assert evidence["passed"] is True
    assert evidence["tests_run"] == 1
    assert evidence["test_code_executed"] is True
    assert evidence["target_unchanged"] is True
    assert "--noconftest" in command
    assert "no:cacheprovider" in command
    assert "--maxfail=1" in command
    assert "--tb=no" in command
    assert str(target.resolve()) == command[-1]
    assert kwargs["shell"] is False
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["cwd"] == root.resolve()
    assert kwargs["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_run_treats_test_failure_as_verified_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_fail.py"
    target.write_text("def test_no():\n    assert False\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=1)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["passed"] is False
    assert evidence["failures"] == 1
    assert evidence["pytest_exit_code"] == 1
    assert "error" not in evidence


def test_run_blocks_changed_target_before_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_change.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    target.write_text("def test_ok():\n    assert False\n", encoding="utf-8")

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("pytest must not start after hash mismatch")

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        must_not_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "TEST_TARGET_CHANGED_AFTER_PREVIEW"
    assert evidence["test_code_executed"] is False


def test_run_reports_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_timeout.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "PYTEST_TIMEOUT"
    assert evidence["test_code_executed"] is True


def test_run_rejects_operational_pytest_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_internal.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        return subprocess.CompletedProcess(command, 3)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "PYTEST_PROCESS_FAILED"
    assert evidence["pytest_exit_code"] == 3


def test_catalog_registers_strict_single_path_pytest_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    schema = definitions["run_python_unit_test_file"].parameters

    assert set(schema["properties"]) == {"path"}
    assert set(schema["required"]) == {"path"}
    assert schema["additionalProperties"] is False

    request = catalog.build_action_request(
        ToolCall(
            name="run_python_unit_test_file",
            arguments={"path": r" C:\Repo\tests\unit\test_one.py "},
        )
    )
    assert request.arguments == {
        "path": r"C:\Repo\tests\unit\test_one.py"
    }


def test_bootstrap_registers_python_unit_test_action() -> None:
    registry = build_action_registry()
    assert registry.contains("run_python_unit_test_file") is True
    request = ActionRequest(
        action="run_python_unit_test_file",
        arguments={"path": r"C:\Temp\test_sample.py"},
    )
    assert registry.risk_for(request) is ActionRisk.PRIVILEGED


class _PytestProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="run_python_unit_test_file",
                    arguments={
                        "path": r"C:\Repo\tests\unit\test_one.py",
                    },
                    call_id="pytest_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Teste recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_tool_gate_does_not_execute_pytest_before_confirmation() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(str(request.arguments["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Teste executado.",
            evidence={"passed": True},
        )

    registry.register(
        RunPythonUnitTestFileAction.name,
        handler,
        risk=RunPythonUnitTestFileAction.risk,
        confirmation_preview=lambda request: None,
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _PytestProvider(),
        registry,
        catalog,
    ).execute(
        "Rode o teste.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_python_unit_test_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={
                "path": r"C:\Repo\tests\unit\test_one.py",
            },
        )
    )

    assert message == (
        r"Executando teste unitário Python C:\Repo\tests\unit\test_one.py..."
    )

def _write_junit_cases(
    command: list[str],
    cases: str,
    *,
    tests: int,
    failures: int,
    errors: int = 0,
) -> None:
    report_arg = next(item for item in command if item.startswith("--junitxml="))
    report = Path(report_arg.split("=", 1)[1])
    report.write_text(
        (
            '<testsuites><testsuite '
            f'tests="{tests}" failures="{failures}" errors="{errors}" skipped="0">'
            f"{cases}"
            "</testsuite></testsuites>"
        ),
        encoding="utf-8",
    )


def test_run_exposes_bounded_failure_diagnostic_without_failure_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_failure_detail.py"
    target.write_text("def test_no():\n    assert False\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    long_message = "bounded failure " + ("x" * 400)

    def fake_run(command, **kwargs):
        _ = kwargs
        cases = (
            '<testcase classname="tests.unit.test_failure_detail" name="test_no">'
            f'<failure message="{long_message}">'
            "TRACEBACK_BODY_MUST_NOT_LEAK"
            "</failure></testcase>"
        )
        _write_junit_cases(list(command), cases, tests=1, failures=1)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    diagnostics = evidence["failure_diagnostics"]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["kind"] == "failure"
    assert diagnostic["test_name"] == "test_no"
    assert diagnostic["class_name"] == "tests.unit.test_failure_detail"
    assert len(diagnostic["message"]) == 240
    assert diagnostic["message"].endswith("…")
    assert "TRACEBACK_BODY_MUST_NOT_LEAK" not in repr(evidence)
    assert evidence["junit_failure_body_returned"] is False
    assert evidence["failure_diagnostics_untrusted"] is True


def test_run_caps_failure_diagnostics_at_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_many_failures.py"
    target.write_text("def test_no():\n    assert False\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        cases = "".join(
            (
                f'<testcase classname="suite" name="test_{index}">'
                f'<failure message="failure {index}">BODY_{index}</failure>'
                "</testcase>"
            )
            for index in range(5)
        )
        _write_junit_cases(list(command), cases, tests=5, failures=5)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["failure_diagnostic_total"] == 5
    assert len(evidence["failure_diagnostics"]) == 3
    assert evidence["failure_diagnostics_truncated"] is True
    assert [item["test_name"] for item in evidence["failure_diagnostics"]] == [
        "test_0",
        "test_1",
        "test_2",
    ]


def test_run_exposes_error_kind_and_bounds_identifiers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_error_detail.py"
    target.write_text("def test_error():\n    raise RuntimeError\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        cases = (
            f'<testcase classname="{"C" * 220}" name="{"N" * 220}">'
            '<error message="collection error&#10;second line">SECRET_BODY</error>'
            "</testcase>"
        )
        _write_junit_cases(list(command), cases, tests=1, failures=0, errors=1)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    diagnostic = evidence["failure_diagnostics"][0]
    assert diagnostic["kind"] == "error"
    assert len(diagnostic["test_name"]) == 160
    assert len(diagnostic["class_name"]) == 160
    assert diagnostic["message"] == "collection error second line"
    assert "SECRET_BODY" not in repr(evidence)


def test_action_failure_result_keeps_structured_diagnostics() -> None:
    class FakeAdapter:
        def run_test_file(
            self,
            raw_path,
            *,
            expected_path,
            expected_sha256,
            expected_project_python_manifest_sha256,
        ):
            _ = (
                raw_path,
                expected_path,
                expected_sha256,
                expected_project_python_manifest_sha256,
            )
            return {
                "path": r"C:\Repo\tests\unit\test_failure.py",
                "tests_run": 1,
                "failures": 1,
                "errors": 0,
                "skipped": 0,
                "passed": False,
                "no_tests_collected": False,
                "failure_diagnostic_total": 1,
                "failure_diagnostics": [
                    {
                        "kind": "failure",
                        "test_name": "test_expected_value",
                        "class_name": "tests.unit.test_failure",
                        "message": "assert 1 == 2",
                    }
                ],
                "failure_diagnostics_truncated": False,
                "failure_diagnostics_untrusted": True,
                "junit_failure_body_returned": False,
            }

    action = RunPythonUnitTestFileAction(FakeAdapter())
    result = action.execute(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={
                "path": r"C:\Repo\tests\unit\test_failure.py",
                "_expected_test_path": r"C:\Repo\tests\unit\test_failure.py",
                "_expected_test_sha256": "a" * 64,
                "_expected_project_python_manifest_sha256": "b" * 64,
            },
        )
    )

    assert result.success is True
    assert result.evidence["failure_diagnostics"][0]["test_name"] == (
        "test_expected_value"
    )
    assert "1 diagnóstico(s) limitado(s)" in result.message


def test_catalog_documents_failure_diagnostics_without_new_authority() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 42
    assert set(definition.parameters["properties"]) == {"path"}
    assert "até 3 diagnósticos" in definition.description
    assert "corpo de traceback" in definition.description

def test_preview_includes_bounded_project_python_manifest(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_manifest.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = root / "src" / "theos" / "feature.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_target(str(target))

    assert len(str(evidence["project_python_manifest_sha256"])) == 64
    assert evidence["project_python_file_count"] == 3
    assert evidence["project_python_total_bytes"] > 0
    assert evidence["project_python_manifest_roots"] == [
        "src/theos",
        "tests/unit",
    ]
    assert "project_python_manifest_entries" not in evidence
    assert "project_python_source" not in evidence


def test_project_manifest_changes_when_source_changes(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_state.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = root / "src" / "theos" / "feature.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    adapter = WindowsPythonUnitTestAdapter(root)

    before = adapter.preview_test_target(str(target))
    source.write_text("VALUE = 2\n", encoding="utf-8")
    after = adapter.preview_test_target(str(target))

    assert before["sha256"] == after["sha256"]
    assert (
        before["project_python_manifest_sha256"]
        != after["project_python_manifest_sha256"]
    )


def test_run_blocks_project_python_change_after_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_guard_before.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = root / "src" / "theos" / "feature.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    source.write_text("VALUE = 2\n", encoding="utf-8")

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("pytest must not start after project-state mismatch")

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        must_not_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "PROJECT_PYTHON_STATE_CHANGED_AFTER_PREVIEW"
    assert evidence["test_code_executed"] is False


def test_run_invalidates_if_project_python_changes_during_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_guard_during.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = root / "src" / "theos" / "feature.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=0)
        source.write_text("VALUE = 2\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "PROJECT_PYTHON_STATE_CHANGED_DURING_RUN"
    assert evidence["test_code_executed"] is True
    assert evidence["project_python_state_unchanged"] is False


def test_run_invalidates_if_python_file_is_added_during_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_guard_added.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=0)
        (unit / "new_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        "theos.integrations.windows.python_tests.subprocess.run",
        fake_run,
    )

    evidence = adapter.run_test_file(
        str(target),
        expected_path=str(preview["path"]),
        expected_sha256=str(preview["sha256"]),
        expected_project_python_manifest_sha256=str(
            preview["project_python_manifest_sha256"]
        ),
    )

    assert evidence["error"] == "PROJECT_PYTHON_STATE_CHANGED_DURING_RUN"
    assert evidence["project_python_state_unchanged"] is False


def test_project_manifest_rejects_oversized_python_file(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_limit.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    source = root / "src" / "theos" / "oversized.py"
    source.write_bytes(b"x" * (256 * 1024 + 1))

    evidence = WindowsPythonUnitTestAdapter(root).preview_test_target(str(target))

    assert evidence["error"] == "PROJECT_PYTHON_FILE_TOO_LARGE"
    assert "project_python_manifest_sha256" not in evidence


def test_action_preview_binds_project_python_manifest(tmp_path: Path) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_action_manifest.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))

    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    manifest = preview.execution_guard[
        "_expected_project_python_manifest_sha256"
    ]
    assert len(manifest) == 64
    assert "Manifesto Python do projeto" in preview.text
    assert "src/theos + tests/unit" in preview.text


def test_catalog_documents_project_python_state_guard_without_schema_change() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 42
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert "manifesto SHA-256" in definition.description
    assert "src/theos" in definition.description
    assert "tests/unit" in definition.description
