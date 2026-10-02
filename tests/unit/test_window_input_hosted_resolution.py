from __future__ import annotations

import inspect

from theos.core.keyboard_keys import build_window_key_tool_description
from theos.core.keyboard_shortcuts import build_window_shortcut_tool_description
from theos.core.mouse_anchors import build_mouse_anchor_click_tool_description
from theos.core.mouse_clicks import build_mouse_click_tool_description
from theos.core.mouse_drags import build_mouse_drag_tool_description
from theos.core.mouse_gestures import build_mouse_double_click_tool_description
from theos.core.mouse_scroll import build_mouse_scroll_tool_description
from theos.core.tools import build_default_tool_catalog
from theos.core.window_targets import build_hosted_window_target_guidance
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter

_INPUT_METHODS = (
    "click_window_center",
    "move_cursor_window_anchor",
    "scroll_window_center",
    "click_window_anchor",
    "double_click_window_center",
    "double_click_window_anchor",
    "drag_window_anchor",
    "scroll_window_anchor",
    "press_key",
    "press_shortcut",
    "type_text",
)

_INPUT_SCHEMAS = {
    "click_window": {"pid", "title", "target_token", "button"},
    "move_cursor_window_anchor": {"pid", "title", "target_token", "anchor"},
    "scroll_window": {"pid", "title", "target_token", "direction"},
    "click_window_anchor": {"pid", "title", "target_token", "button", "anchor"},
    "double_click_window": {"pid", "title", "target_token", "gesture"},
    "double_click_window_anchor": {
        "pid",
        "title",
        "target_token",
        "gesture",
        "anchor",
    },
    "drag_window_anchor": {
        "pid",
        "title",
        "target_token",
        "gesture",
        "source_anchor",
        "target_anchor",
    },
    "scroll_window_anchor": {
        "pid",
        "title",
        "target_token",
        "direction",
        "anchor",
    },
    "press_key": {"pid", "title", "target_token", "key"},
    "press_shortcut": {"pid", "title", "target_token", "shortcut"},
    "type_text": {"pid", "title", "target_token", "text"},
}


def test_input_tool_schemas_are_unchanged_and_exact() -> None:
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    for name, expected_properties in _INPUT_SCHEMAS.items():
        schema = definitions[name].parameters
        assert set(schema["properties"]) == expected_properties
        assert set(schema["required"]) == expected_properties
        assert schema["additionalProperties"] is False


def test_registry_owned_catalog_descriptions_remain_builder_owned() -> None:
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    expected = {
        "click_window": build_mouse_click_tool_description(),
        "scroll_window": build_mouse_scroll_tool_description(),
        "click_window_anchor": build_mouse_anchor_click_tool_description(),
        "double_click_window": build_mouse_double_click_tool_description(),
        "drag_window_anchor": build_mouse_drag_tool_description(),
        "press_key": build_window_key_tool_description(),
        "press_shortcut": build_window_shortcut_tool_description(),
    }
    for name, description in expected.items():
        assert definitions[name].description == description


def test_all_input_descriptions_share_hosted_alias_guidance() -> None:
    guidance = build_hosted_window_target_guidance()
    assert "ApplicationFrameHost.exe" in guidance
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    for name in _INPUT_SCHEMAS:
        assert guidance in definitions[name].description


def test_all_input_methods_reuse_hosted_exact_target_resolver() -> None:
    for method_name in _INPUT_METHODS:
        source = inspect.getsource(
            getattr(WindowsDesktopWindowAdapter, method_name)
        )
        assert source.count("self._resolve_exact_window_target(") == 1
        assert "user32.EnumWindows(callback, 0)" not in source


def test_all_input_methods_report_hosted_resolution_evidence() -> None:
    for method_name in _INPUT_METHODS:
        source = inspect.getsource(
            getattr(WindowsDesktopWindowAdapter, method_name)
        )
        assert '"hosted_visual_frame_resolution": True' in source
        assert '"visual_frame_normalized": visual_frame_normalized' in source
        assert '"resolved_window_class": resolved_candidate.class_name' in source
        assert (
            "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution"
            in source
        )


def test_shared_resolver_remains_input_transport_free() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._resolve_exact_window_target
    )
    assert source.count("self._enumerate_action_window_candidates(") == 1
    assert "user32.EnumWindows(callback, 0)" not in source
    assert "DwmGetWindowAttribute" not in source
    assert "resolve_hosted_visual_frame_for_single_placement" in source
    assert "SendInput" not in source
    assert "SetCursorPos" not in source


def test_input_transport_fingerprints_remain_registered_and_bounded() -> None:
    cursor = inspect.getsource(
        WindowsDesktopWindowAdapter.move_cursor_window_anchor
    )
    key = inspect.getsource(WindowsDesktopWindowAdapter.press_key)
    shortcut = inspect.getsource(WindowsDesktopWindowAdapter.press_shortcut)
    text = inspect.getsource(WindowsDesktopWindowAdapter.type_text)

    assert "SendInput(" not in cursor
    assert "SetCursorPos(" in cursor
    assert "event_array_type = _Input * len(events)" in key
    assert "event_array_type = _Input * len(events)" in shortcut
    assert "KEYEVENTF_UNICODE" in text
    assert "clipboard_used" in text
