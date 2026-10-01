from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ClickWindowAction
from theos.core.mouse_clicks import (
    ALLOWED_MOUSE_BUTTONS,
    MOUSE_BUTTON_REGISTRY,
    MOUSE_BUTTON_SPECS,
)
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import (
    _MOUSE_BUTTON_FLAGS,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
)


class _FakeMouseAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def click_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        button: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, button))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "button": button,
            "position_mode": "window_center",
            "click_screen_x": 640,
            "click_screen_y": 480,
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
                "window_center_cursor_sendinput_count_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{button}",
            "button_allowlist": list(ALLOWED_MOUSE_BUTTONS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_mouse_button_registry_is_single_policy_source() -> None:
    assert tuple(MOUSE_BUTTON_REGISTRY) == ALLOWED_MOUSE_BUTTONS
    assert tuple(MOUSE_BUTTON_REGISTRY.values()) == MOUSE_BUTTON_SPECS
    assert ALLOWED_MOUSE_BUTTONS == ("LEFT", "RIGHT", "MIDDLE")
    for spec in MOUSE_BUTTON_SPECS:
        assert spec.risk is ActionRisk.CONFIRM
        assert spec.preview_effect


def test_mouse_button_transport_mapping_covers_registry() -> None:
    assert set(_MOUSE_BUTTON_FLAGS) == set(ALLOWED_MOUSE_BUTTONS)
    assert _MOUSE_BUTTON_FLAGS == {
        "LEFT": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "RIGHT": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "MIDDLE": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }


def test_click_window_preview_guard_and_registry_risk() -> None:
    adapter = _FakeMouseAdapter()
    action = ClickWindowAction(adapter)
    request = ActionRequest(
        action="click_window",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "button": "RIGHT",
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MOUSE_CLICK_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "CLICAR CENTRO DA JANELA" in preview.text
    assert "Botão: RIGHT" in preview.text
    assert "centro da janela" in preview.text
    assert "menu de contexto" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "RIGHT")
    ]
    assert result.evidence["input_events_submitted"] == 2
    assert result.evidence["cursor_position_verified"] is True
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_registered_mouse_buttons() -> None:
    catalog = build_default_tool_catalog()

    for button in ALLOWED_MOUSE_BUTTONS:
        request = catalog.build_action_request(
            ToolCall(
                name="click_window",
                arguments={
                    "pid": 5001,
                    "title": " Bloco de Notas ",
                    "target_token": "b" * 64,
                    "button": button,
                },
            )
        )
        assert request.action == "click_window"
        assert request.arguments == {
            "pid": 5001,
            "title": "Bloco de Notas",
            "target_token": "b" * 64,
            "button": button,
        }


def test_catalog_rejects_unlisted_mouse_button_and_coordinates() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="click_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "button": "DOUBLE_LEFT",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="click_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "button": "LEFT",
                    "x": 10,
                    "y": 10,
                },
            )
        )


def test_mouse_tool_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["click_window"].parameters

    assert tuple(schema["properties"]["button"]["enum"]) == ALLOWED_MOUSE_BUTTONS
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "button",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
