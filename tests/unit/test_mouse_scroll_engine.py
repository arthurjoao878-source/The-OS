from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ScrollWindowAction
from theos.core.mouse_scroll import (
    ALLOWED_MOUSE_SCROLL_DIRECTIONS,
    MOUSE_SCROLL_REGISTRY,
    MOUSE_SCROLL_SPECS,
)
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import (
    _MOUSE_WHEEL_DELTAS,
    MOUSEEVENTF_WHEEL,
    WHEEL_DELTA,
)


class _FakeMouseScrollAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def scroll_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        direction: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, direction))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "direction": direction,
            "position_mode": "window_center",
            "scroll_units": 1,
            "wheel_delta": _MOUSE_WHEEL_DELTAS[direction],
            "click_screen_x": 640,
            "click_screen_y": 480,
            "cursor_position_verified": True,
            "input_events_submitted": 1,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "window_center_cursor_wheel_sendinput_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_WHEEL_{direction}",
            "direction_allowlist": list(ALLOWED_MOUSE_SCROLL_DIRECTIONS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_mouse_scroll_registry_is_single_policy_source() -> None:
    assert tuple(MOUSE_SCROLL_REGISTRY) == ALLOWED_MOUSE_SCROLL_DIRECTIONS
    assert tuple(MOUSE_SCROLL_REGISTRY.values()) == MOUSE_SCROLL_SPECS
    assert ALLOWED_MOUSE_SCROLL_DIRECTIONS == ("UP", "DOWN")
    for spec in MOUSE_SCROLL_SPECS:
        assert spec.risk is ActionRisk.CONFIRM
        assert spec.preview_effect


def test_mouse_wheel_transport_mapping_is_bounded() -> None:
    assert set(_MOUSE_WHEEL_DELTAS) == set(ALLOWED_MOUSE_SCROLL_DIRECTIONS)
    assert _MOUSE_WHEEL_DELTAS == {
        "UP": WHEEL_DELTA,
        "DOWN": -WHEEL_DELTA,
    }
    assert MOUSEEVENTF_WHEEL == 0x0800


def test_scroll_window_preview_guard_and_registry_risk() -> None:
    adapter = _FakeMouseScrollAdapter()
    action = ScrollWindowAction(adapter)
    request = ActionRequest(
        action="scroll_window",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "direction": "DOWN",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_SCROLL_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "ROLAR JANELA" in preview.text
    assert "Direção: DOWN" in preview.text
    assert "centro geométrico" in preview.text
    assert "uma unidade fixa" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "DOWN")
    ]
    assert result.evidence["input_events_submitted"] == 1
    assert result.evidence["scroll_units"] == 1
    assert result.evidence["wheel_delta"] == -WHEEL_DELTA
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_mouse_scroll_directions() -> None:
    catalog = build_default_tool_catalog()

    for direction in ALLOWED_MOUSE_SCROLL_DIRECTIONS:
        request = catalog.build_action_request(
            ToolCall(
                name="scroll_window",
                arguments={
                    "pid": 5001,
                    "title": " Bloco de Notas ",
                    "target_token": "b" * 64,
                    "direction": direction,
                },
            )
        )
        assert request.action == "scroll_window"
        assert request.arguments == {
            "pid": 5001,
            "title": "Bloco de Notas",
            "target_token": "b" * 64,
            "direction": direction,
        }


def test_catalog_rejects_unlisted_scroll_or_arbitrary_amount() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="scroll_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "direction": "LEFT",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="scroll_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "direction": "DOWN",
                    "amount": 20,
                },
            )
        )


def test_mouse_scroll_tool_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["scroll_window"].parameters

    assert (
        tuple(schema["properties"]["direction"]["enum"])
        == ALLOWED_MOUSE_SCROLL_DIRECTIONS
    )
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "direction",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
