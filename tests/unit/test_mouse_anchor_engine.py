from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ClickWindowAnchorAction
from theos.core.mouse_anchors import (
    ALLOWED_MOUSE_ANCHORS,
    MOUSE_ANCHOR_REGISTRY,
    MOUSE_ANCHOR_SPECS,
)
from theos.core.mouse_clicks import ALLOWED_MOUSE_BUTTONS
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeMouseAnchorAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str, str]] = []

    def click_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        button: str,
        anchor: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, button, anchor))
        spec = MOUSE_ANCHOR_REGISTRY[anchor]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "button": button,
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
            "input_events_submitted": 2,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_cursor_sendinput_count_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{button}_ANCHOR_{anchor}",
            "button_allowlist": list(ALLOWED_MOUSE_BUTTONS),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_mouse_anchor_registry_is_fixed_internal_quadrants() -> None:
    assert tuple(MOUSE_ANCHOR_REGISTRY) == ALLOWED_MOUSE_ANCHORS
    assert tuple(MOUSE_ANCHOR_REGISTRY.values()) == MOUSE_ANCHOR_SPECS
    assert ALLOWED_MOUSE_ANCHORS == (
        "UPPER_LEFT",
        "UPPER_RIGHT",
        "LOWER_LEFT",
        "LOWER_RIGHT",
    )
    assert {
        spec.name: (spec.x_percent, spec.y_percent)
        for spec in MOUSE_ANCHOR_SPECS
    } == {
        "UPPER_LEFT": (25, 25),
        "UPPER_RIGHT": (75, 25),
        "LOWER_LEFT": (25, 75),
        "LOWER_RIGHT": (75, 75),
    }


def test_mouse_anchor_points_are_strictly_inside_client_area() -> None:
    for spec in MOUSE_ANCHOR_SPECS:
        assert 0 < spec.x_percent < 100
        assert 0 < spec.y_percent < 100
        assert spec.x_percent in {25, 75}
        assert spec.y_percent in {25, 75}


def test_click_window_anchor_preview_guard_and_button_risk() -> None:
    adapter = _FakeMouseAnchorAdapter()
    action = ClickWindowAnchorAction(adapter)
    request = ActionRequest(
        action="click_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "button": "RIGHT",
            "anchor": "UPPER_LEFT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_ANCHOR_CLICK_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "CLICAR ÂNCORA INTERNA DA JANELA" in preview.text
    assert "Botão: RIGHT" in preview.text
    assert "Âncora: UPPER_LEFT" in preview.text
    assert "25% da largura" in preview.text
    assert "25% da altura" in preview.text
    assert "Operação registrada: clicar com o botão direito" in preview.text
    assert "controle sob esse ponto" in preview.text
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
            "RIGHT",
            "UPPER_LEFT",
        )
    ]
    assert result.evidence["input_events_submitted"] == 2
    assert result.evidence["position_mode"] == "client_anchor"
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_mouse_anchor_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="click_window_anchor",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "button": "LEFT",
                "anchor": "LOWER_RIGHT",
            },
        )
    )
    assert request.action == "click_window_anchor"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "button": "LEFT",
        "anchor": "LOWER_RIGHT",
    }


def test_catalog_rejects_arbitrary_anchor_coordinates() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="click_window_anchor",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "button": "LEFT",
                    "anchor": "CENTER",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="click_window_anchor",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "button": "LEFT",
                    "anchor": "UPPER_LEFT",
                    "x": 10,
                    "y": 10,
                },
            )
        )


def test_mouse_anchor_tool_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["click_window_anchor"].parameters

    assert tuple(schema["properties"]["button"]["enum"]) == ALLOWED_MOUSE_BUTTONS
    assert tuple(schema["properties"]["anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "button",
        "anchor",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
