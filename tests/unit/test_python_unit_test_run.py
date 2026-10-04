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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
            expected_pytest_verifier_path,
            expected_pytest_verifier_sha256,
            expected_pytest_package_manifest_sha256,
            expected_python_runtime_state_sha256,
        ):
            _ = (
                raw_path,
                expected_path,
                expected_sha256,
                expected_project_python_manifest_sha256,
                expected_pytest_verifier_path,
                expected_pytest_verifier_sha256,
                expected_pytest_package_manifest_sha256,
                expected_python_runtime_state_sha256,
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
                "_expected_pytest_verifier_path": r"C:\Venv\pytest.exe",
                "_expected_pytest_verifier_sha256": "c" * 64,
                "_expected_pytest_package_manifest_sha256": "d" * 64,
                "_expected_python_runtime_state_sha256": "e" * 64,
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

    assert len(definitions) == 53
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
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

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert "manifesto SHA-256" in definition.description
    assert "src/theos" in definition.description
    assert "tests/unit" in definition.description

def test_run_scrubs_ambient_pytest_option_and_plugin_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_env_isolation.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    captured: dict[str, object] = {}

    monkeypatch.setenv("PYTEST_ADDOPTS", r"C:\Injected\test_extra.py")
    monkeypatch.setenv("PYTEST_PLUGINS", "injected.plugin")
    monkeypatch.setenv("PYTEST_DEBUG", "1")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["env"] = kwargs["env"]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    env = captured["env"]
    assert evidence["passed"] is True
    assert "PYTEST_ADDOPTS" not in env
    assert "PYTEST_PLUGINS" not in env
    assert "PYTEST_DEBUG" not in env
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert evidence["ambient_pytest_environment_scrubbed"] is True


def test_run_uses_private_empty_pytest_config_and_fixed_rootdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_config_isolation.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / "pytest.ini").write_text(
        "[pytest]\naddopts = C:\\Injected\\test_extra.py\n",
        encoding="utf-8",
    )
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
        config_index = command.index("-c") + 1
        config_path = Path(command[config_index])
        captured["config_path"] = config_path
        captured["config_text"] = config_path.read_text(encoding="utf-8")
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    command = captured["command"]
    config_path = captured["config_path"]
    assert evidence["passed"] is True
    assert captured["config_text"] == "[pytest]\n"
    assert config_path != (root / "pytest.ini")
    assert command[command.index("--rootdir") + 1] == str(root.resolve())
    assert evidence["implicit_pytest_config_enabled"] is False


def test_run_command_keeps_one_explicit_target_under_ambient_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_single_target.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    injected = unit / "test_injected.py"
    injected.write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    captured: dict[str, object] = {}

    monkeypatch.setenv("PYTEST_ADDOPTS", str(injected))
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["env"] = kwargs["env"]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    command = captured["command"]
    assert evidence["passed"] is True
    assert command[-1] == str(target.resolve())
    assert str(injected.resolve()) not in command
    assert "PYTEST_ADDOPTS" not in captured["env"]


def test_action_preview_discloses_pytest_invocation_isolation(
    tmp_path: Path,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_preview_isolation.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))

    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert preview.allowed is True
    assert "configuração pytest implícita desabilitada" in preview.text
    assert "PYTEST_ADDOPTS/PYTEST_PLUGINS herdados removidos" in preview.text


def test_catalog_documents_pytest_invocation_isolation_without_schema_change() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "config pytest temporário vazio" in definition.description
    assert "PYTEST_ADDOPTS" in definition.description
    assert "PYTEST_PLUGINS" in definition.description

def test_run_scrubs_ambient_python_environment_and_sets_controlled_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_python_env.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    captured: dict[str, object] = {}

    ambient = {
        "PYTHONPATH": r"C:\Injected",
        "PYTHONHOME": r"C:\WrongPython",
        "PYTHONINSPECT": "1",
        "PYTHONWARNINGS": "error",
        "PYTHONBREAKPOINT": "injected.module:hook",
        "PYTHONUSERBASE": r"C:\InjectedUserBase",
        "PYTHONCASEOK": "1",
        "PYTHONOPTIMIZE": "2",
    }
    for key, value in ambient.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    env = captured["env"]
    assert evidence["passed"] is True
    for key in ambient:
        assert key not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONSAFEPATH"] == "1"
    assert evidence["ambient_python_environment_scrubbed"] is True
    assert evidence["python_user_site_enabled"] is False
    assert evidence["python_safe_path_enabled"] is True
    assert evidence["python_import_environment_is_hermetic"] is False


def test_run_preserves_unrelated_environment_while_scrubbing_python_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_env_preserve.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"")
    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    captured: dict[str, object] = {}

    monkeypatch.setenv("M78_KEEP_ME", "present")
    monkeypatch.setenv("PYTHONPATH", r"C:\Injected")
    monkeypatch.setenv("PYTEST_ADDOPTS", r"C:\Injected\test_extra.py")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    env = captured["env"]
    assert evidence["passed"] is True
    assert env["M78_KEEP_ME"] == "present"
    assert "PYTHONPATH" not in env
    assert "PYTEST_ADDOPTS" not in env


def test_run_evidence_marks_python_import_policy_as_non_hermetic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_non_hermetic.py"
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
        expected_pytest_verifier_path=str(
            adapter.preview_pytest_verifier()["pytest_verifier_path"]
        ),
        expected_pytest_verifier_sha256=str(
            adapter.preview_pytest_verifier()["pytest_verifier_sha256"]
        ),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    assert evidence["ambient_python_environment_scrubbed"] is True
    assert evidence["python_user_site_enabled"] is False
    assert evidence["python_safe_path_enabled"] is True
    assert evidence["python_import_environment_is_hermetic"] is False
    assert evidence["venv_site_packages_may_execute_startup_hooks"] is True


def test_action_preview_discloses_controlled_python_import_environment(
    tmp_path: Path,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_preview_python_env.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))

    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert preview.allowed is True
    assert "PYTHON* herdadas são removidas" in preview.text
    assert "PYTHONNOUSERSITE=1" in preview.text
    assert "PYTHONSAFEPATH=1" in preview.text
    assert "não torna imports herméticos" in preview.text


def test_catalog_documents_controlled_python_import_environment() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "PYTHONPATH/PYTHONHOME" in definition.description
    assert "PYTHONNOUSERSITE=1" in definition.description
    assert "PYTHONSAFEPATH=1" in definition.description
    assert "não é hermético" in definition.description

def test_preview_hashes_fixed_pytest_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M79_VERIFIER_BYTES")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_pytest_verifier()

    assert evidence["pytest_verifier_path"] == str(fake_pytest.resolve())
    assert len(str(evidence["pytest_verifier_sha256"])) == 64
    assert evidence["pytest_verifier_size_bytes"] == len(b"M79_VERIFIER_BYTES")
    assert evidence["pytest_verifier_hash_only_preflight"] is True


def test_run_blocks_changed_pytest_verifier_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_verifier_before.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M79_BEFORE")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()
    fake_pytest.write_bytes(b"M79_AFTER")

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("pytest must not start after verifier hash mismatch")

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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    assert evidence["error"] == "PYTEST_VERIFIER_CHANGED_AFTER_PREVIEW"
    assert evidence["test_code_executed"] is False


def test_run_invalidates_if_pytest_verifier_changes_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_verifier_during.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M79_BEFORE")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=0)
        fake_pytest.write_bytes(b"M79_AFTER")
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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    assert evidence["error"] == "PYTEST_VERIFIER_CHANGED_DURING_RUN"
    assert evidence["test_code_executed"] is True
    assert evidence["pytest_verifier_unchanged"] is False


def test_preview_rejects_oversized_pytest_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_pytest_verifier()

    assert evidence["error"] == "PYTEST_VERIFIER_TOO_LARGE"
    assert "pytest_verifier_sha256" not in evidence


def test_action_preview_binds_pytest_verifier_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_action_verifier.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M79_ACTION_VERIFIER")
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )

    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))
    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert preview.allowed is True
    assert preview.execution_guard["_expected_pytest_verifier_path"] == str(
        fake_pytest.resolve()
    )
    assert len(
        preview.execution_guard["_expected_pytest_verifier_sha256"]
    ) == 64
    assert "pytest.exe aprovado" in preview.text
    assert "SHA-256 do pytest.exe" in preview.text


def test_catalog_documents_pytest_verifier_identity_guard() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "pytest.exe" in definition.description
    assert "SHA-256" in definition.description
    assert "revalidado antes e depois" in definition.description

def _m80_fake_package_roots(tmp_path: Path) -> tuple[Path, Path]:
    site_packages = tmp_path / "site-packages"
    pytest_root = site_packages / "pytest"
    core_root = site_packages / "_pytest"
    pytest_root.mkdir(parents=True)
    core_root.mkdir(parents=True)
    (pytest_root / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (core_root / "__init__.py").write_text("CORE = 1\n", encoding="utf-8")
    return pytest_root, core_root


def test_preview_hashes_bounded_pytest_package_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    pytest_root, core_root = _m80_fake_package_roots(tmp_path)
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_package_roots",
        staticmethod(lambda: (pytest_root, core_root)),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_pytest_package_state()

    assert len(str(evidence["pytest_package_manifest_sha256"])) == 64
    assert evidence["pytest_package_file_count"] == 2
    assert evidence["pytest_package_total_bytes"] > 0
    assert evidence["pytest_package_manifest_roots"] == ["pytest", "_pytest"]
    assert evidence["pytest_package_manifest_entries_returned"] is False
    assert evidence["pytest_package_content_returned"] is False


def test_preview_rejects_oversized_pytest_package_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    pytest_root, core_root = _m80_fake_package_roots(tmp_path)
    (core_root / "oversized.bin").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_package_roots",
        staticmethod(lambda: (pytest_root, core_root)),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_pytest_package_state()

    assert evidence["error"] == "PYTEST_PACKAGE_FILE_TOO_LARGE"
    assert "pytest_package_manifest_sha256" not in evidence


def test_run_blocks_changed_pytest_package_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_package_before.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M80_VERIFIER")
    pytest_root, core_root = _m80_fake_package_roots(tmp_path)
    package_file = core_root / "__init__.py"

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_package_roots",
        staticmethod(lambda: (pytest_root, core_root)),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()
    package_state = adapter.preview_pytest_package_state()
    package_file.write_text("CORE = 2\n", encoding="utf-8")

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("pytest must not start after package-state mismatch")

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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            package_state["pytest_package_manifest_sha256"]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    assert evidence["error"] == "PYTEST_PACKAGE_STATE_CHANGED_AFTER_PREVIEW"
    assert evidence["test_code_executed"] is False


def test_run_invalidates_if_pytest_package_changes_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_package_during.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M80_VERIFIER")
    pytest_root, core_root = _m80_fake_package_roots(tmp_path)
    package_file = core_root / "__init__.py"

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_package_roots",
        staticmethod(lambda: (pytest_root, core_root)),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()
    package_state = adapter.preview_pytest_package_state()

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=0)
        package_file.write_text("CORE = 2\n", encoding="utf-8")
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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            package_state["pytest_package_manifest_sha256"]
        ),
        expected_python_runtime_state_sha256=str(
            adapter.preview_python_runtime_state()[
                "python_runtime_state_sha256"
            ]
        ),
    )

    assert evidence["error"] == "PYTEST_PACKAGE_STATE_CHANGED_DURING_RUN"
    assert evidence["test_code_executed"] is True
    assert evidence["pytest_package_state_unchanged"] is False


def test_action_preview_binds_pytest_package_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_action_package_state.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M80_VERIFIER")
    pytest_root, core_root = _m80_fake_package_roots(tmp_path)

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_package_roots",
        staticmethod(lambda: (pytest_root, core_root)),
    )

    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))
    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert preview.allowed is True
    manifest = preview.execution_guard[
        "_expected_pytest_package_manifest_sha256"
    ]
    assert len(manifest) == 64
    assert "Manifesto pytest/_pytest" in preview.text
    assert "não é dependency closure" in preview.text


def test_catalog_documents_pytest_package_state_guard() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "pytest/_pytest" in definition.description
    assert "manifesto SHA-256" in definition.description
    assert "dependency closure" in definition.description

def _m81_fake_runtime_state(tmp_path: Path) -> tuple[Path, Path]:
    venv_root = tmp_path / "venv"
    scripts = venv_root / "Scripts"
    scripts.mkdir(parents=True)
    runtime = scripts / "python.exe"
    config = venv_root / "pyvenv.cfg"
    runtime.write_bytes(b"M81_PYTHON_RUNTIME")
    config.write_text("home = C:\\Python\n", encoding="utf-8")
    return runtime, config


def test_preview_hashes_python_runtime_bootstrap_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    runtime, config = _m81_fake_runtime_state(tmp_path)
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_python_runtime_executable",
        staticmethod(lambda: runtime),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_python_runtime_state()

    assert evidence["python_runtime_path"] == str(runtime.resolve())
    assert evidence["pyvenv_config_path"] == str(config.resolve())
    assert len(str(evidence["python_runtime_sha256"])) == 64
    assert len(str(evidence["pyvenv_config_sha256"])) == 64
    assert len(str(evidence["python_runtime_state_sha256"])) == 64
    assert evidence["python_runtime_state_content_returned"] is False


def test_preview_rejects_oversized_pyvenv_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _project(tmp_path)
    runtime, config = _m81_fake_runtime_state(tmp_path)
    config.write_bytes(b"x" * (64 * 1024 + 1))
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_python_runtime_executable",
        staticmethod(lambda: runtime),
    )

    evidence = WindowsPythonUnitTestAdapter(root).preview_python_runtime_state()

    assert evidence["error"] == "PYVENV_CONFIG_TOO_LARGE"
    assert "python_runtime_state_sha256" not in evidence


def test_run_blocks_changed_python_runtime_state_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_runtime_before.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M81_VERIFIER")
    runtime, config = _m81_fake_runtime_state(tmp_path)

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_python_runtime_executable",
        staticmethod(lambda: runtime),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()
    runtime_state = adapter.preview_python_runtime_state()
    config.write_text("home = C:\\Changed\n", encoding="utf-8")

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("pytest must not start after runtime-state mismatch")

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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            runtime_state["python_runtime_state_sha256"]
        ),
    )

    assert evidence["error"] == "PYTHON_RUNTIME_STATE_CHANGED_AFTER_PREVIEW"
    assert evidence["test_code_executed"] is False


def test_run_invalidates_if_python_runtime_state_changes_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_runtime_during.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    fake_pytest = tmp_path / "pytest.exe"
    fake_pytest.write_bytes(b"M81_VERIFIER")
    runtime, config = _m81_fake_runtime_state(tmp_path)

    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_pytest_executable",
        staticmethod(lambda: fake_pytest),
    )
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_python_runtime_executable",
        staticmethod(lambda: runtime),
    )

    adapter = WindowsPythonUnitTestAdapter(root)
    preview = adapter.preview_test_target(str(target))
    verifier = adapter.preview_pytest_verifier()
    runtime_state = adapter.preview_python_runtime_state()

    def fake_run(command, **kwargs):
        _ = kwargs
        _write_junit(list(command), tests=1, failures=0)
        config.write_text("home = C:\\Changed\n", encoding="utf-8")
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
        expected_pytest_verifier_path=str(verifier["pytest_verifier_path"]),
        expected_pytest_verifier_sha256=str(verifier["pytest_verifier_sha256"]),
        expected_pytest_package_manifest_sha256=str(
            adapter.preview_pytest_package_state()[
                "pytest_package_manifest_sha256"
            ]
        ),
        expected_python_runtime_state_sha256=str(
            runtime_state["python_runtime_state_sha256"]
        ),
    )

    assert evidence["error"] == "PYTHON_RUNTIME_STATE_CHANGED_DURING_RUN"
    assert evidence["test_code_executed"] is True
    assert evidence["python_runtime_state_unchanged"] is False


def test_action_preview_binds_python_runtime_bootstrap_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, unit = _project(tmp_path)
    target = unit / "test_action_runtime_state.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    runtime, _ = _m81_fake_runtime_state(tmp_path)
    monkeypatch.setattr(
        WindowsPythonUnitTestAdapter,
        "_python_runtime_executable",
        staticmethod(lambda: runtime),
    )

    action = RunPythonUnitTestFileAction(WindowsPythonUnitTestAdapter(root))
    preview = action.confirmation_preview(
        ActionRequest(
            action="run_python_unit_test_file",
            arguments={"path": str(target)},
        )
    )

    assert preview.allowed is True
    digest = preview.execution_guard[
        "_expected_python_runtime_state_sha256"
    ]
    assert len(digest) == 64
    assert "Estado bootstrap Python do venv" in preview.text
    assert "pyvenv.cfg" in preview.text
    assert "não é runtime dependency closure" in preview.text


def test_catalog_documents_python_runtime_bootstrap_state_guard() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["run_python_unit_test_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "Scripts/python.exe" in definition.description
    assert "pyvenv.cfg" in definition.description
    assert "runtime dependency closure" in definition.description
