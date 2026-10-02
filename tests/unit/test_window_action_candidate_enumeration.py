from __future__ import annotations

import inspect

from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter


def test_action_candidate_helper_owns_one_enumwindows_and_dwm_pass() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._enumerate_action_window_candidates
    )
    assert source.count("user32.EnumWindows(callback, 0)") == 1
    assert "DwmGetWindowAttribute" in source
    assert "GetClassNameW" in source
    assert "GetClientRect" in source
    assert "visible_pids.add(candidate_pid)" in source


def test_exact_resolver_consumes_action_candidate_helper_only() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._resolve_exact_window_target
    )
    assert source.count("self._enumerate_action_window_candidates(") == 1
    assert "user32.EnumWindows(callback, 0)" not in source
    assert "DwmGetWindowAttribute" not in source
    assert "pid in visible_pids" in source
    assert "WINDOW_TARGET_TOKEN_STALE" in source
    assert "WINDOW_TARGET_TITLE_CHANGED" in source


def test_pair_layout_consumes_shared_candidate_helper_once() -> None:
    source = inspect.getsource(WindowsDesktopWindowAdapter.place_window_pair)
    assert source.count("self._enumerate_action_window_candidates(") == 1
    assert "user32.EnumWindows(callback, 0)" not in source
    assert "DwmGetWindowAttribute" not in source
    assert "resolve_hosted_visual_frame_with_dwm_tiebreak" in source
    assert "WINDOW_PAIR_ROLLBACK_FAILED" in source


def test_set_layout_consumes_shared_candidate_helper_once() -> None:
    source = inspect.getsource(WindowsDesktopWindowAdapter.place_window_set)
    assert source.count("self._enumerate_action_window_candidates(") == 1
    assert "user32.EnumWindows(callback, 0)" not in source
    assert "DwmGetWindowAttribute" not in source
    assert "resolve_hosted_visual_frame_for_set" in source
    assert "WINDOW_SET_ROLLBACK_FAILED" in source


def test_discovery_keeps_narrow_independent_enumeration() -> None:
    for method_name in ("snapshot", "snapshot_many"):
        source = inspect.getsource(
            getattr(WindowsDesktopWindowAdapter, method_name)
        )
        assert source.count("user32.EnumWindows(callback, 0)") == 1
        assert "_enumerate_action_window_candidates" not in source
        assert "GetClassNameW" not in source
        assert "DwmGetWindowAttribute" not in source


def test_action_candidate_helper_has_no_mutation_transport() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._enumerate_action_window_candidates
    )
    assert "MoveWindow" not in source
    assert "ShowWindow" not in source
    assert "SetForegroundWindow" not in source
    assert "SendInput" not in source
    assert "SetCursorPos" not in source
