from __future__ import annotations

import inspect

from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter

_SINGLE_TARGET_METHODS = (
    "activate_window",
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
    "place_window",
    "restore_window",
    "maximize_window",
    "minimize_window",
    "close_window",
)


def test_exact_single_target_resolver_has_generic_private_name() -> None:
    assert hasattr(WindowsDesktopWindowAdapter, "_resolve_exact_window_target")
    assert not hasattr(WindowsDesktopWindowAdapter, "_resolve_window_state_target")


def test_all_single_target_methods_use_shared_exact_resolver() -> None:
    for method_name in _SINGLE_TARGET_METHODS:
        source = inspect.getsource(
            getattr(WindowsDesktopWindowAdapter, method_name)
        )
        assert source.count("self._resolve_exact_window_target(") == 1
        assert "user32.EnumWindows(callback, 0)" not in source


def test_place_window_preserves_placement_specific_hosted_errors() -> None:
    source = inspect.getsource(WindowsDesktopWindowAdapter.place_window)
    assert "WINDOW_VISUAL_FRAME_NOT_FOUND" in source
    assert "WINDOW_PLACEMENT_VISUAL_FRAME_NOT_FOUND" in source
    assert "WINDOW_VISUAL_FRAME_AMBIGUOUS" in source
    assert "WINDOW_PLACEMENT_VISUAL_FRAME_AMBIGUOUS" in source


def test_place_window_transport_and_restore_invariants_remain_present() -> None:
    source = inspect.getsource(WindowsDesktopWindowAdapter.place_window)
    assert "SW_RESTORE" in source
    assert "MonitorFromWindow" in source
    assert "GetMonitorInfoW" in source
    assert "MoveWindow" in source
    assert "GetWindowRect" in source
    assert "WINDOW_PLACEMENT_NOT_VERIFIED" in source
    assert "DwmGetWindowAttribute" not in source


def test_shared_exact_resolver_remains_transport_free() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._resolve_exact_window_target
    )
    assert source.count("user32.EnumWindows(callback, 0)") == 1
    assert "DwmGetWindowAttribute" in source
    assert "resolve_hosted_visual_frame_for_single_placement" in source
    assert "MoveWindow" not in source
    assert "SendInput" not in source
    assert "SetCursorPos" not in source
