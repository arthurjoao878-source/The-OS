from __future__ import annotations

from theos.core.actions.contracts import ActionRequest
from theos.core.actions.desktop_windows import PressKeyAction
from theos.core.keyboard_keys import (
    ALLOWED_WINDOW_KEYS,
    WINDOW_KEY_REGISTRY,
    WINDOW_KEY_SPECS,
    build_window_key_tool_description,
    format_window_key_allowlist_pt,
)
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import _WINDOW_KEY_VK_CODES


def test_keyboard_key_registry_is_single_policy_source() -> None:
    assert tuple(WINDOW_KEY_REGISTRY) == ALLOWED_WINDOW_KEYS
    assert tuple(WINDOW_KEY_REGISTRY.values()) == WINDOW_KEY_SPECS
    assert len(WINDOW_KEY_SPECS) == len(set(ALLOWED_WINDOW_KEYS))
    for spec in WINDOW_KEY_SPECS:
        assert spec.name == spec.name.upper()
        assert spec.name
        assert spec.intent_pt
        assert spec.preview_effect


def test_key_action_policy_and_preview_are_registry_driven() -> None:
    allowed_text = format_window_key_allowlist_pt()
    for index, spec in enumerate(WINDOW_KEY_SPECS, start=1):
        request = ActionRequest(
            action="press_key",
            arguments={
                "pid": 6000 + index,
                "title": "Bloco de Notas",
                "target_token": f"{index:x}" * 64,
                "key": spec.name,
            },
        )
        assert PressKeyAction.risk_for(request) is spec.risk
        preview = PressKeyAction.confirmation_preview(request)
        assert preview.allowed is True
        assert f"Tecla: {spec.name}" in preview.text
        assert spec.preview_effect in preview.text
        assert f"Somente {allowed_text} estão permitidas" in preview.text


def test_key_catalog_enum_and_description_are_registry_driven() -> None:
    catalog = build_default_tool_catalog()
    definitions = {definition.name: definition for definition in catalog.definitions()}
    key_definition = definitions["press_key"]
    assert tuple(key_definition.parameters["properties"]["key"]["enum"]) == ALLOWED_WINDOW_KEYS
    assert key_definition.description == build_window_key_tool_description()
    for index, spec in enumerate(WINDOW_KEY_SPECS, start=1):
        request = catalog.build_action_request(
            ToolCall(
                name="press_key",
                arguments={
                    "pid": 7000 + index,
                    "title": "Bloco de Notas",
                    "target_token": f"{index:x}" * 64,
                    "key": spec.name,
                },
            )
        )
        assert request.arguments["key"] == spec.name


def test_windows_key_transport_mapping_covers_registry() -> None:
    assert set(_WINDOW_KEY_VK_CODES) == set(ALLOWED_WINDOW_KEYS)
