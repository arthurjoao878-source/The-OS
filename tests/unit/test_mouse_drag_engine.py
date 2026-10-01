from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import DragWindowAnchorAction
from theos.core.mouse_anchors import ALLOWED_MOUSE_ANCHORS, MOUSE_ANCHOR_REGISTRY
from theos.core.mouse_drags import (
    ALLOWED_MOUSE_DRAGS,
    MOUSE_DRAG_REGISTRY,
    MOUSE_DRAG_SPECS,
)
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import (
    _MOUSE_DRAG_FLAGS,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
)


class _FakeDragAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str, str, str]] = []

    def drag_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
        source_anchor: str,
        target_anchor: str,
    ) -> dict[str, object]:
        self.calls.append(
            (pid, title, target_token, gesture, source_anchor, target_anchor)
        )
        source = MOUSE_ANCHOR_REGISTRY[source_anchor]
        target = MOUSE_ANCHOR_REGISTRY[target_anchor]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "gesture": gesture,
            "source_anchor": source_anchor,
            "target_anchor": target_anchor,
            "source_anchor_x_percent": source.x_percent,
            "source_anchor_y_percent": source.y_percent,
            "target_anchor_x_percent": target.x_percent,
            "target_anchor_y_percent": target.y_percent,
            "position_mode": "client_anchor_to_anchor",
            "source_cursor_position_verified": True,
            "target_cursor_position_verified": True,
            "button_down_events_submitted": 1,
            "button_up_events_submitted": 1,
            "input_events_submitted": 2,
            "foreground_verified_before": True,
            "foreground_verified_during": True,
            "foreground_verified_after": True,
            "input_submission_verified": True,
            "semantic_drag_verified": False,
            "content_effect_verified": False,
        }


def test_mouse_drag_registry_is_single_policy_source() -> None:
    assert tuple(MOUSE_DRAG_REGISTRY) == ALLOWED_MOUSE_DRAGS
    assert tuple(MOUSE_DRAG_REGISTRY.values()) == MOUSE_DRAG_SPECS
    assert ALLOWED_MOUSE_DRAGS == ("LEFT_DRAG",)
    spec = MOUSE_DRAG_REGISTRY["LEFT_DRAG"]
    assert spec.risk is ActionRisk.DESTRUCTIVE
    assert spec.event_count == 2


def test_drag_transport_mapping_is_left_down_then_left_up() -> None:
    assert set(_MOUSE_DRAG_FLAGS) == set(ALLOWED_MOUSE_DRAGS)
    assert _MOUSE_DRAG_FLAGS == {
        "LEFT_DRAG": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    }


def test_drag_preview_guard_risk_and_distinct_anchors() -> None:
    adapter = _FakeDragAdapter()
    action = DragWindowAnchorAction(adapter)
    request = ActionRequest(
        action="drag_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "gesture": "LEFT_DRAG",
            "source_anchor": "UPPER_LEFT",
            "target_anchor": "LOWER_RIGHT",
        },
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_DRAG_PREVIEW_REQUIRED"

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "ARRASTAR ENTRE ÂNCORAS INTERNAS" in preview.text
    assert "Origem: UPPER_LEFT" in preview.text
    assert "Destino: LOWER_RIGHT" in preview.text
    assert "25% da largura" in preview.text
    assert "75% da largura" in preview.text
    assert "LEFTDOWN" in preview.text
    assert "LEFTUP" in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)
    assert result.success is True
    assert adapter.calls == [
        (
            4321,
            "Sem título - Bloco de Notas",
            "a" * 64,
            "LEFT_DRAG",
            "UPPER_LEFT",
            "LOWER_RIGHT",
        )
    ]

    same_anchor = ActionRequest(
        action="drag_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "gesture": "LEFT_DRAG",
            "source_anchor": "UPPER_LEFT",
            "target_anchor": "UPPER_LEFT",
        },
    )
    assert DragWindowAnchorAction.confirmation_preview(same_anchor).allowed is False


def test_catalog_builds_registered_anchor_drag() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="drag_window_anchor",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "gesture": "LEFT_DRAG",
                "source_anchor": "UPPER_RIGHT",
                "target_anchor": "LOWER_LEFT",
            },
        )
    )

    assert request.action == "drag_window_anchor"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "gesture": "LEFT_DRAG",
        "source_anchor": "UPPER_RIGHT",
        "target_anchor": "LOWER_LEFT",
    }


def test_catalog_rejects_invalid_drag_shape() -> None:
    catalog = build_default_tool_catalog()

    invalid_cases = [
        {
            "gesture": "RIGHT_DRAG",
            "source_anchor": "UPPER_LEFT",
            "target_anchor": "LOWER_RIGHT",
        },
        {
            "gesture": "LEFT_DRAG",
            "source_anchor": "CENTER",
            "target_anchor": "LOWER_RIGHT",
        },
        {
            "gesture": "LEFT_DRAG",
            "source_anchor": "UPPER_LEFT",
            "target_anchor": "UPPER_LEFT",
        },
    ]
    for case in invalid_cases:
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="drag_window_anchor",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "c" * 64,
                        **case,
                    },
                )
            )

    for extra in (
        {"x": 10},
        {"y": 20},
        {"duration_ms": 300},
        {"path": [1, 2]},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="drag_window_anchor",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "d" * 64,
                        "gesture": "LEFT_DRAG",
                        "source_anchor": "UPPER_LEFT",
                        "target_anchor": "LOWER_RIGHT",
                        **extra,
                    },
                )
            )


def test_drag_tool_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {definition.name: definition for definition in catalog.definitions()}
    schema = definitions["drag_window_anchor"].parameters

    assert tuple(schema["properties"]["gesture"]["enum"]) == ALLOWED_MOUSE_DRAGS
    assert tuple(schema["properties"]["source_anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert tuple(schema["properties"]["target_anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "gesture",
        "source_anchor",
        "target_anchor",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
