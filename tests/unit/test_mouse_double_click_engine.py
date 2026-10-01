from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import DoubleClickWindowAction
from theos.core.mouse_gestures import (
    ALLOWED_MOUSE_GESTURES,
    MOUSE_GESTURE_REGISTRY,
    MOUSE_GESTURE_SPECS,
)
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import (
    _MOUSE_GESTURE_FLAGS,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
)


class _FakeDoubleClickAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def double_click_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, gesture))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "gesture": gesture,
            "position_mode": "window_center",
            "click_screen_x": 640,
            "click_screen_y": 480,
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
                "window_center_cursor_four_event_sequence_and_foreground_only"
            ),
            "input_method": "SendInput_MOUSE_DOUBLE_LEFT",
            "gesture_allowlist": list(ALLOWED_MOUSE_GESTURES),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_mouse_gesture_registry_is_single_policy_source() -> None:
    assert tuple(MOUSE_GESTURE_REGISTRY) == ALLOWED_MOUSE_GESTURES
    assert tuple(MOUSE_GESTURE_REGISTRY.values()) == MOUSE_GESTURE_SPECS
    assert ALLOWED_MOUSE_GESTURES == ("DOUBLE_LEFT",)
    spec = MOUSE_GESTURE_REGISTRY["DOUBLE_LEFT"]
    assert spec.risk is ActionRisk.CONFIRM
    assert spec.event_count == 4
    assert spec.preview_effect


def test_double_click_transport_mapping_is_exact_four_event_sequence() -> None:
    assert set(_MOUSE_GESTURE_FLAGS) == set(ALLOWED_MOUSE_GESTURES)
    assert _MOUSE_GESTURE_FLAGS == {
        "DOUBLE_LEFT": (
            MOUSEEVENTF_LEFTDOWN,
            MOUSEEVENTF_LEFTUP,
            MOUSEEVENTF_LEFTDOWN,
            MOUSEEVENTF_LEFTUP,
        ),
    }


def test_double_click_preview_guard_and_registry_risk() -> None:
    adapter = _FakeDoubleClickAdapter()
    action = DoubleClickWindowAction(adapter)
    request = ActionRequest(
        action="double_click_window",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "gesture": "DOUBLE_LEFT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_DOUBLE_CLICK_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "DUPLO CLIQUE NO CENTRO DA JANELA" in preview.text
    assert "Gesto: DOUBLE_LEFT" in preview.text
    assert "quatro eventos" in preview.text
    assert "não afirma" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "DOUBLE_LEFT")
    ]
    assert result.evidence["input_events_submitted"] == 4
    assert result.evidence["semantic_double_click_verified"] is False
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_double_click_gesture() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="double_click_window",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "gesture": "DOUBLE_LEFT",
            },
        )
    )

    assert request.action == "double_click_window"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "gesture": "DOUBLE_LEFT",
    }


def test_catalog_rejects_unlisted_gesture_or_arbitrary_click_count() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="double_click_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "gesture": "DOUBLE_RIGHT",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="double_click_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "gesture": "DOUBLE_LEFT",
                    "click_count": 3,
                },
            )
        )


def test_double_click_tool_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["double_click_window"].parameters

    assert tuple(schema["properties"]["gesture"]["enum"]) == ALLOWED_MOUSE_GESTURES
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "gesture",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
