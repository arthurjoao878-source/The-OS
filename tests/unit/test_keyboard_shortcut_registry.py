from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PressShortcutAction
from theos.core.keyboard_keys import WINDOW_KEY_REGISTRY
from theos.core.keyboard_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    WINDOW_SHORTCUT_REGISTRY,
    WINDOW_SHORTCUT_SPECS,
    format_window_shortcut_allowlist_pt,
)
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.windows.desktop_windows import (
    _WINDOW_KEY_VK_CODES,
    _WINDOW_SHORTCUT_VK_PAIRS,
    VK_CONTROL,
)


def test_keyboard_shortcut_registry_is_single_policy_source() -> None:
    assert tuple(WINDOW_SHORTCUT_REGISTRY) == ALLOWED_WINDOW_SHORTCUTS
    assert tuple(WINDOW_SHORTCUT_REGISTRY.values()) == WINDOW_SHORTCUT_SPECS
    assert len(WINDOW_SHORTCUT_SPECS) == len(set(ALLOWED_WINDOW_SHORTCUTS))

    for spec in WINDOW_SHORTCUT_SPECS:
        assert spec.name == f"{spec.modifier}_{spec.primary_key}"
        assert spec.modifier == "CTRL"
        assert (
            (
                len(spec.primary_key) == 1
                and "A" <= spec.primary_key <= "Z"
            )
            or spec.primary_key in WINDOW_KEY_REGISTRY
        )
        assert spec.label == f"CTRL+{spec.primary_key}"


def test_action_policy_and_preview_are_registry_driven() -> None:
    allowed_text = format_window_shortcut_allowlist_pt()

    for index, spec in enumerate(WINDOW_SHORTCUT_SPECS, start=1):
        request = ActionRequest(
            action="press_shortcut",
            arguments={
                "pid": 4000 + index,
                "title": "Bloco de Notas",
                "target_token": f"{index:x}" * 64,
                "shortcut": spec.name,
            },
        )

        assert PressShortcutAction.risk_for(request) is spec.risk
        preview = PressShortcutAction.confirmation_preview(request)
        assert preview.allowed is True
        assert f"Atalho: {spec.label}" in preview.text
        assert spec.preview_effect in preview.text
        assert f"Somente {allowed_text} estão permitidos" in preview.text


def test_catalog_enum_and_validation_are_registry_driven() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    shortcut_schema = definitions["press_shortcut"].parameters

    assert tuple(
        shortcut_schema["properties"]["shortcut"]["enum"]
    ) == ALLOWED_WINDOW_SHORTCUTS

    for index, spec in enumerate(WINDOW_SHORTCUT_SPECS, start=1):
        request = catalog.build_action_request(
            ToolCall(
                name="press_shortcut",
                arguments={
                    "pid": 5000 + index,
                    "title": "Bloco de Notas",
                    "target_token": f"{index:x}" * 64,
                    "shortcut": spec.name,
                },
            )
        )
        assert request.arguments["shortcut"] == spec.name


def test_windows_transport_mapping_is_derived_from_registry() -> None:
    assert set(_WINDOW_SHORTCUT_VK_PAIRS) == set(ALLOWED_WINDOW_SHORTCUTS)

    for spec in WINDOW_SHORTCUT_SPECS:
        primary_vk = (
            ord(spec.primary_key)
            if len(spec.primary_key) == 1 and "A" <= spec.primary_key <= "Z"
            else _WINDOW_KEY_VK_CODES[spec.primary_key]
        )
        assert _WINDOW_SHORTCUT_VK_PAIRS[spec.name] == (
            VK_CONTROL,
            primary_vk,
        )

def test_keyboard_shortcut_batch_1_policy_is_explicit() -> None:
    expected = {
        "CTRL_F": (ActionRisk.CONFIRM, False),
        "CTRL_S": (ActionRisk.DESTRUCTIVE, True),
        "CTRL_Y": (ActionRisk.DESTRUCTIVE, True),
    }

    for shortcut, (risk, content_mutation_expected) in expected.items():
        spec = WINDOW_SHORTCUT_REGISTRY[shortcut]
        assert spec.risk is risk
        assert spec.content_mutation_expected is content_mutation_expected
        assert spec.clipboard_used is False
        assert spec.clipboard_effect_expected is False
        assert spec.clipboard_input_expected is False

def test_keyboard_ctrl_navigation_batch_policy_is_explicit() -> None:
    expected = {
        "CTRL_LEFT": "LEFT",
        "CTRL_RIGHT": "RIGHT",
        "CTRL_UP": "UP",
        "CTRL_DOWN": "DOWN",
        "CTRL_HOME": "HOME",
        "CTRL_END": "END",
    }

    for shortcut, primary_key in expected.items():
        spec = WINDOW_SHORTCUT_REGISTRY[shortcut]
        assert spec.primary_key == primary_key
        assert spec.risk is ActionRisk.CONFIRM
        assert spec.content_mutation_expected is False
        assert spec.clipboard_used is False
        assert spec.clipboard_effect_expected is False
        assert spec.clipboard_input_expected is False
