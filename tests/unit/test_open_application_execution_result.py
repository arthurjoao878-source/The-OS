from __future__ import annotations

from theos.core.actions.contracts import ActionRequest
from theos.core.actions.open_application import OpenApplicationAction
from theos.core.applications.registry import ApplicationRegistry


class _FakeWindowsApplicationAdapter:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.launches = 0

    def launch(self, _app) -> int:
        self.launches += 1
        return 4242

    def verify_running(self, _app) -> dict[str, object]:
        return {
            "verified": self.verified,
            "matched_processes": 1 if self.verified else 0,
        }


def _action(monkeypatch, *, verified: bool = True) -> OpenApplicationAction:
    monkeypatch.setattr(
        "theos.core.applications.registry.shutil.which",
        lambda name: r"C:\Windows\System32\notepad.exe"
        if name == "notepad.exe"
        else None,
    )
    return OpenApplicationAction(
        ApplicationRegistry(),
        _FakeWindowsApplicationAdapter(verified=verified),
    )


def test_open_application_reports_dispatch_and_verified_postcondition(monkeypatch) -> None:
    action = _action(monkeypatch, verified=True)
    result = action.execute(
        ActionRequest(
            action="open_application",
            arguments={"application": "notepad"},
        )
    )

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["verified"] is True
    assert result.evidence["launch_pid"] == 4242


def test_open_application_separates_dispatch_from_failed_postcondition(monkeypatch) -> None:
    action = _action(monkeypatch, verified=False)
    result = action.execute(
        ActionRequest(
            action="open_application",
            arguments={"application": "notepad"},
        )
    )

    assert result.success is False
    assert result.effect_dispatched is True
    assert result.postcondition_verified is False
    assert result.error_code == "ACTION_VERIFICATION_FAILED"
    assert result.evidence["launch_pid"] == 4242


def test_open_application_validation_failure_proves_no_dispatch() -> None:
    adapter = _FakeWindowsApplicationAdapter()
    action = OpenApplicationAction(ApplicationRegistry(), adapter)

    result = action.execute(
        ActionRequest(
            action="open_application",
            arguments={"application": ""},
        )
    )

    assert result.success is False
    assert result.effect_dispatched is False
    assert result.postcondition_verified is None
    assert adapter.launches == 0
