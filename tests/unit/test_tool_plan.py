from __future__ import annotations

import pytest

from theos.core.tools import MAX_TOOL_PLAN_STEPS, ToolCall, ToolPlan


def test_tool_plan_preserves_proposed_order() -> None:
    plan = ToolPlan(
        calls=(
            ToolCall(name="open_application", arguments={"application": "Notepad"}),
            ToolCall(name="open_application", arguments={"application": "Chrome"}),
        )
    )

    assert [call.arguments["application"] for call in plan.calls] == [
        "Notepad",
        "Chrome",
    ]


def test_tool_plan_is_bounded() -> None:
    calls = tuple(
        ToolCall(
            name="open_application",
            arguments={"application": f"App {index}"},
        )
        for index in range(MAX_TOOL_PLAN_STEPS + 1)
    )

    with pytest.raises(ValueError):
        ToolPlan(calls=calls)
