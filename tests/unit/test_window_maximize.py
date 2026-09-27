from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import MaximizeWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def maximize_window(self, pid: int, title: str) -> dict[str, object]:
        self.calls.append((pid, title))
        return {
            "pid": pid,
            "title": title,
            "process_name": "CalculatorApp.exe",
            "maximized": True,
            "maximized_verified": True,
            "already_maximized": False,
            "title_match": "bounded_title_exact",
        }


def test_maximize_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = MaximizeWindowAction(adapter)
    request = ActionRequest(
        action="maximize_window",
        arguments={"pid": 4321, "title": "Calculadora"},
    )

    assert action.risk is ActionRisk.NORMAL

    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [(4321, "Calculadora")]
    assert result.evidence["maximized_verified"] is True
    assert "PID 4321" in result.message


def test_catalog_builds_maximize_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="maximize_window",
            arguments={"pid": 4321, "title": " Calculadora "},
        )
    )

    assert request.action == "maximize_window"
    assert request.arguments == {"pid": 4321, "title": "Calculadora"}


def test_catalog_rejects_invalid_maximize_window_target() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="maximize_window",
                arguments={"pid": 0, "title": "Calculadora"},
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid PID must be rejected")
