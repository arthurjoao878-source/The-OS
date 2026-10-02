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
    unit.mkdir(parents=True)
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
