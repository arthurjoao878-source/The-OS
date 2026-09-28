from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import MinimizeWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def minimize_window(
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
            "minimized": True,
            "minimized_verified": True,
            "already_minimized": False,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_minimize_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = MinimizeWindowAction(adapter)
    request = ActionRequest(
        action="minimize_window",
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
    assert result.evidence["minimized_verified"] is True
    assert result.evidence["title_match"] == (
        "pid_bounded_title_and_opaque_token_exact"
    )
    assert "PID 4321" in result.message


def test_catalog_builds_minimize_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="minimize_window",
            arguments={
                "pid": 4321,
                "title": " Calculadora ",
                "target_token": "b" * 64,
            },
        )
    )

    assert request.action == "minimize_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "Calculadora",
        "target_token": "b" * 64,
    }


def test_catalog_rejects_invalid_minimize_window_target() -> None:
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
                    name="minimize_window",
                    arguments=arguments,
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid minimize-window target must be rejected")
