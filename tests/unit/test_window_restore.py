from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import RestoreWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def restore_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token))
        return {
            "pid": pid,
            "title": title,
            "process_name": "CalculatorApp.exe",
            "target_token": target_token,
            "restored": True,
            "restored_verified": True,
            "was_minimized": False,
            "was_maximized": True,
            "state": "normal",
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_restore_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = RestoreWindowAction(adapter)
    request = ActionRequest(
        action="restore_window",
        arguments={
            "pid": 4321,
            "title": "Calculadora",
            "target_token": "a" * 64,
        },
    )

    assert action.risk is ActionRisk.NORMAL

    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [(4321, "Calculadora", "a" * 64)]
    assert result.evidence["target_token"] == "a" * 64
    assert result.evidence["restored_verified"] is True
    assert result.evidence["state"] == "normal"
    assert result.evidence["title_match"] == (
        "pid_bounded_title_and_opaque_token_exact"
    )
    assert "PID 4321" in result.message


def test_catalog_builds_restore_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="restore_window",
            arguments={
                "pid": 4321,
                "title": " Calculadora ",
                "target_token": "b" * 64,
            },
        )
    )

    assert request.action == "restore_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "Calculadora",
        "target_token": "b" * 64,
    }


def test_catalog_rejects_invalid_restore_window_target() -> None:
    catalog = build_default_tool_catalog()

    for arguments in (
        {
            "pid": 0,
            "title": "Calculadora",
            "target_token": "c" * 64,
        },
        {
            "pid": 4321,
            "title": "Calculadora",
            "target_token": "BAD",
        },
    ):
        try:
            catalog.build_action_request(
                ToolCall(
                    name="restore_window",
                    arguments=arguments,
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid restore-window target must be rejected")
