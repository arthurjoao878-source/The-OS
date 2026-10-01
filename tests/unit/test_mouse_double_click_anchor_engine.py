from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import DoubleClickWindowAnchorAction
from theos.core.mouse_anchors import ALLOWED_MOUSE_ANCHORS, MOUSE_ANCHOR_REGISTRY
from theos.core.mouse_gestures import ALLOWED_MOUSE_GESTURES
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeDoubleClickAnchorAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str, str]] = []

    def double_click_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
        anchor: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, gesture, anchor))
        spec = MOUSE_ANCHOR_REGISTRY[anchor]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "gesture": gesture,
            "anchor": anchor,
            "anchor_label_pt": spec.label_pt,
            "anchor_x_percent": spec.x_percent,
            "anchor_y_percent": spec.y_percent,
            "position_mode": "client_anchor",
            "client_width": 800,
            "client_height": 600,
            "click_screen_x": 300,
            "click_screen_y": 250,
            "cursor_position_verified": True,
            "input_events_submitted": 4,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "semantic_double_click_verified": False,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_cursor_four_event_sequence_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{gesture}_ANCHOR_{anchor}",
            "gesture_allowlist": list(ALLOWED_MOUSE_GESTURES),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_double_click_anchor_uses_existing_gesture_and_anchor_registries() -> None:
    assert ALLOWED_MOUSE_GESTURES == ("DOUBLE_LEFT",)
    assert ALLOWED_MOUSE_ANCHORS == (
        "UPPER_LEFT",
        "TOP_CENTER",
        "UPPER_RIGHT",
        "CENTER_LEFT",
        "CENTER_RIGHT",
        "LOWER_LEFT",
        "BOTTOM_CENTER",
        "LOWER_RIGHT",
    )


def test_double_click_anchor_preview_guard_and_risk() -> None:
    adapter = _FakeDoubleClickAnchorAdapter()
    action = DoubleClickWindowAnchorAction(adapter)
    request = ActionRequest(
        action="double_click_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "gesture": "DOUBLE_LEFT",
            "anchor": "LOWER_RIGHT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_DOUBLE_CLICK_ANCHOR_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "DUPLO CLIQUE EM ÂNCORA INTERNA" in preview.text
    assert "Gesto: DOUBLE_LEFT" in preview.text
    assert "Âncora: LOWER_RIGHT" in preview.text
    assert "75% da largura" in preview.text
    assert "75% da altura" in preview.text
    assert "quatro eventos LEFT down/up/down/up" in preview.text
    assert "centro da janela" not in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (
            4321,
            "Sem título - Bloco de Notas",
            "a" * 64,
            "DOUBLE_LEFT",
            "LOWER_RIGHT",
        )
    ]
    assert result.evidence["input_events_submitted"] == 4
    assert result.evidence["position_mode"] == "client_anchor"
    assert result.evidence["semantic_double_click_verified"] is False
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_double_click_anchor_request() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="double_click_window_anchor",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "gesture": "DOUBLE_LEFT",
                "anchor": "UPPER_RIGHT",
            },
        )
    )

    assert request.action == "double_click_window_anchor"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "gesture": "DOUBLE_LEFT",
        "anchor": "UPPER_RIGHT",
    }


def test_catalog_rejects_unlisted_gesture_or_anchor() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="double_click_window_anchor",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "gesture": "DOUBLE_RIGHT",
                    "anchor": "UPPER_LEFT",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="double_click_window_anchor",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "gesture": "DOUBLE_LEFT",
                    "anchor": "CENTER",
                },
            )
        )


def test_catalog_rejects_arbitrary_coordinates_or_click_count() -> None:
    catalog = build_default_tool_catalog()

    for extra in (
        {"x": 10},
        {"y": 20},
        {"click_count": 3},
        {"interval_ms": 250},
    ):
        arguments = {
            "pid": 5001,
            "title": "Bloco de Notas",
            "target_token": "d" * 64,
            "gesture": "DOUBLE_LEFT",
            "anchor": "UPPER_LEFT",
            **extra,
        }
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="double_click_window_anchor",
                    arguments=arguments,
                )
            )


def test_double_click_anchor_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["double_click_window_anchor"].parameters

    assert tuple(schema["properties"]["gesture"]["enum"]) == ALLOWED_MOUSE_GESTURES
    assert tuple(schema["properties"]["anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "gesture",
        "anchor",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
