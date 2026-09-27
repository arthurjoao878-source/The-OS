from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.processes import TerminateProcessAction
from theos.integrations.windows import processes as processes_module
from theos.integrations.windows.processes import WindowsProcessAdapter
from theos.shell.assistant.main_window import MainWindow


class _FakeProcess:
    def __init__(
        self,
        *,
        pid: int,
        name: str,
        create_time: float,
    ) -> None:
        self.pid = pid
        self._name = name
        self._create_time = create_time
        self.terminate_calls = 0
        self.wait_calls = 0
        self.running = True

    def name(self) -> str:
        return self._name

    def create_time(self) -> float:
        return self._create_time

    def terminate(self) -> None:
        self.terminate_calls += 1

    def wait(self, *, timeout: float):
        assert timeout == 3.0
        self.wait_calls += 1
        self.running = False
        return 0

    def is_running(self) -> bool:
        return self.running


def test_windows_process_termination_revalidates_and_verifies(monkeypatch) -> None:
    fake = _FakeProcess(pid=4321, name="notepad.exe", create_time=123.5)

    monkeypatch.setattr(processes_module.os, "getpid", lambda: 9999)
    monkeypatch.setattr(
        processes_module.psutil,
        "Process",
        lambda pid: fake if pid == 4321 else None,
    )

    adapter = WindowsProcessAdapter()
    preview = adapter.preview_terminate_process(4321)

    assert preview == {
        "pid": 4321,
        "allowed": True,
        "name": "notepad.exe",
        "create_time": 123.5,
    }
    assert fake.terminate_calls == 0

    result = adapter.terminate_process(
        4321,
        expected_name="notepad.exe",
        expected_create_time=123.5,
    )

    assert result["terminated"] is True
    assert result["verified_exited"] is True
    assert result["kill_fallback_used"] is False
    assert fake.terminate_calls == 1
    assert fake.wait_calls == 1


def test_windows_process_termination_blocks_protected_process(monkeypatch) -> None:
    protected = _FakeProcess(pid=500, name="lsass.exe", create_time=100.0)

    monkeypatch.setattr(processes_module.os, "getpid", lambda: 9999)
    monkeypatch.setattr(
        processes_module.psutil,
        "Process",
        lambda pid: protected if pid == 500 else None,
    )

    preview = WindowsProcessAdapter().preview_terminate_process(500)

    assert preview["allowed"] is False
    assert preview["error"] == "PROTECTED_PROCESS"
    assert protected.terminate_calls == 0


class _FakeTerminationAdapter:
    def __init__(self) -> None:
        self.terminate_calls = 0

    @staticmethod
    def preview_terminate_process(pid: int) -> dict[str, object]:
        return {
            "pid": pid,
            "allowed": True,
            "name": "notepad.exe",
            "create_time": 55.0,
        }

    def terminate_process(
        self,
        pid: int,
        *,
        expected_name: str,
        expected_create_time: float,
    ) -> dict[str, object]:
        self.terminate_calls += 1
        assert pid == 4321
        assert expected_name == "notepad.exe"
        assert expected_create_time == 55.0
        return {
            "pid": pid,
            "name": expected_name,
            "create_time": expected_create_time,
            "terminated": True,
            "verified_exited": True,
            "exit_code": 0,
            "termination_method": "psutil_terminate",
            "kill_fallback_used": False,
        }


def test_terminate_action_requires_preview_guard() -> None:
    adapter = _FakeTerminationAdapter()
    action = TerminateProcessAction(adapter)
    request = ActionRequest(
        action="terminate_process",
        arguments={"pid": 4321},
    )

    assert action.risk is ActionRisk.DESTRUCTIVE

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "PROCESS_TERMINATION_PREVIEW_REQUIRED"
    assert adapter.terminate_calls == 0

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "ENCERRAR PROCESSO" in preview.text
    assert "notepad.exe" in preview.text
    assert "trabalho não salvo" in preview.text
    assert adapter.terminate_calls == 0

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.terminate_calls == 1
    assert "notepad.exe" in result.message


def test_terminate_process_subject_uses_pid() -> None:
    request = ActionRequest(
        action="terminate_process",
        arguments={"pid": 4321},
    )

    assert MainWindow._action_subject(request) == "PID 4321"
