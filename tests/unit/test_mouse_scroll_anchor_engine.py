from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ScrollWindowAnchorAction
from theos.core.mouse_anchors import ALLOWED_MOUSE_ANCHORS, MOUSE_ANCHOR_REGISTRY
from theos.core.mouse_scroll import ALLOWED_MOUSE_SCROLL_DIRECTIONS
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeScrollAnchorAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str, str]] = []

    def scroll_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        direction: str,
        anchor: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, direction, anchor))
        spec = MOUSE_ANCHOR_REGISTRY[anchor]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "direction": direction,
            "anchor": anchor,
            "anchor_label_pt": spec.label_pt,
            "anchor_x_percent": spec.x_percent,
            "anchor_y_percent": spec.y_percent,
            "position_mode": "client_anchor",
            "scroll_units": 1,
            "wheel_delta": -120 if direction == "DOWN" else 120,
            "cursor_screen_x": 700,
            "cursor_screen_y": 500,
            "cursor_position_verified": True,
            "input_events_submitted": 1,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "client_anchor_cursor_wheel_sendinput_and_foreground_only",
            "input_method": f"SendInput_MOUSE_WHEEL_{direction}_ANCHOR_{anchor}",
            "direction_allowlist": list(ALLOWED_MOUSE_SCROLL_DIRECTIONS),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_scroll_anchor_reuses_existing_registries() -> None:
    assert ALLOWED_MOUSE_SCROLL_DIRECTIONS == ("UP", "DOWN")
    assert ALLOWED_MOUSE_ANCHORS == (
        "UPPER_LEFT",
        "UPPER_RIGHT",
        "LOWER_LEFT",
        "LOWER_RIGHT",
    )


def test_scroll_anchor_preview_guard_and_risk() -> None:
    adapter = _FakeScrollAnchorAdapter()
    action = ScrollWindowAnchorAction(adapter)
    request = ActionRequest(
        action="scroll_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "direction": "DOWN",
            "anchor": "LOWER_RIGHT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_SCROLL_ANCHOR_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "ROLAR EM ÂNCORA INTERNA" in preview.text
    assert "Direção: DOWN" in preview.text
    assert "Âncora: LOWER_RIGHT" in preview.text
    assert "75% da largura" in preview.text
    assert "75% da altura" in preview.text
    assert "uma unidade fixa" in preview.text
    assert "centro da janela" not in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "DOWN", "LOWER_RIGHT")
    ]
    assert result.evidence["position_mode"] == "client_anchor"
    assert result.evidence["scroll_units"] == 1
    assert result.evidence["input_events_submitted"] == 1
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_anchor_scroll() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="scroll_window_anchor",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "direction": "UP",
                "anchor": "UPPER_RIGHT",
            },
        )
    )

    assert request.action == "scroll_window_anchor"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "direction": "UP",
        "anchor": "UPPER_RIGHT",
    }


def test_catalog_rejects_unlisted_direction_or_anchor() -> None:
    catalog = build_default_tool_catalog()

    for direction, anchor in (
        ("LEFT", "UPPER_LEFT"),
        ("DOWN", "CENTER"),
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="scroll_window_anchor",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "c" * 64,
                        "direction": direction,
                        "anchor": anchor,
                    },
                )
            )


def test_catalog_rejects_arbitrary_scroll_anchor_parameters() -> None:
    catalog = build_default_tool_catalog()

    for extra in (
        {"amount": 3},
        {"x": 10},
        {"y": 20},
        {"horizontal": True},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="scroll_window_anchor",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "d" * 64,
                        "direction": "DOWN",
                        "anchor": "LOWER_LEFT",
                        **extra,
                    },
                )
            )


def test_scroll_anchor_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {definition.name: definition for definition in catalog.definitions()}
    schema = definitions["scroll_window_anchor"].parameters

    assert tuple(schema["properties"]["direction"]["enum"]) == (
        ALLOWED_MOUSE_SCROLL_DIRECTIONS
    )
    assert tuple(schema["properties"]["anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "direction",
        "anchor",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
