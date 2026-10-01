from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import MoveCursorWindowAnchorAction
from theos.core.mouse_anchors import ALLOWED_MOUSE_ANCHORS, MOUSE_ANCHOR_REGISTRY
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeMoveCursorAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def move_cursor_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        anchor: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, anchor))
        spec = MOUSE_ANCHOR_REGISTRY[anchor]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "anchor": anchor,
            "anchor_label_pt": spec.label_pt,
            "anchor_x_percent": spec.x_percent,
            "anchor_y_percent": spec.y_percent,
            "position_mode": "client_anchor",
            "client_width": 800,
            "client_height": 600,
            "cursor_screen_x": 600,
            "cursor_screen_y": 450,
            "cursor_position_verified": True,
            "input_events_submitted": 0,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "cursor_move_verified": True,
            "hover_effect_verified": False,
            "content_effect_verified": False,
            "verification": "client_anchor_cursor_position_and_foreground_only",
            "input_method": "SetCursorPos_ONLY",
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_move_cursor_anchor_reuses_anchor_registry() -> None:
    assert ALLOWED_MOUSE_ANCHORS == (
        "UPPER_LEFT",
        "UPPER_RIGHT",
        "LOWER_LEFT",
        "LOWER_RIGHT",
    )


def test_move_cursor_preview_guard_and_risk() -> None:
    adapter = _FakeMoveCursorAdapter()
    action = MoveCursorWindowAnchorAction(adapter)
    request = ActionRequest(
        action="move_cursor_window_anchor",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "anchor": "UPPER_RIGHT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_MOVE_ANCHOR_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "MOVER CURSOR PARA ÂNCORA INTERNA" in preview.text
    assert "Âncora: UPPER_RIGHT" in preview.text
    assert "75% da largura" in preview.text
    assert "25% da altura" in preview.text
    assert "Nenhum clique" in preview.text
    assert "wheel" in preview.text.lower()
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "UPPER_RIGHT")
    ]
    assert result.evidence["position_mode"] == "client_anchor"
    assert result.evidence["input_events_submitted"] == 0
    assert result.evidence["cursor_move_verified"] is True
    assert result.evidence["hover_effect_verified"] is False
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_cursor_move() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="move_cursor_window_anchor",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "anchor": "LOWER_LEFT",
            },
        )
    )

    assert request.action == "move_cursor_window_anchor"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "anchor": "LOWER_LEFT",
    }


def test_catalog_rejects_unlisted_cursor_anchor() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="move_cursor_window_anchor",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "anchor": "CENTER",
                },
            )
        )


def test_catalog_rejects_arbitrary_cursor_move_parameters() -> None:
    catalog = build_default_tool_catalog()

    for extra in (
        {"x": 10},
        {"y": 20},
        {"button": "LEFT"},
        {"duration_ms": 300},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="move_cursor_window_anchor",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "d" * 64,
                        "anchor": "LOWER_RIGHT",
                        **extra,
                    },
                )
            )


def test_move_cursor_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {definition.name: definition for definition in catalog.definitions()}
    schema = definitions["move_cursor_window_anchor"].parameters

    assert tuple(schema["properties"]["anchor"]["enum"]) == ALLOWED_MOUSE_ANCHORS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "anchor",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
