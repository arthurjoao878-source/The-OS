from __future__ import annotations

from theos.core.window_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    DESTRUCTIVE_WINDOW_SHORTCUTS,
    PRIVILEGED_WINDOW_SHORTCUTS,
    is_allowed_window_shortcut,
    is_destructive_window_shortcut,
    is_privileged_window_shortcut,
)


def test_window_shortcut_allowlist_is_exact_and_bounded() -> None:
    assert ALLOWED_WINDOW_SHORTCUTS == ("CTRL_A", "CTRL_C", "CTRL_X", "CTRL_V", "CTRL_Z")
    assert DESTRUCTIVE_WINDOW_SHORTCUTS == frozenset({"CTRL_X", "CTRL_Z"})
    assert PRIVILEGED_WINDOW_SHORTCUTS == frozenset({"CTRL_V"})
    assert is_allowed_window_shortcut("CTRL_A") is True
    assert is_allowed_window_shortcut("CTRL_C") is True
    assert is_allowed_window_shortcut("CTRL_X") is True
    assert is_allowed_window_shortcut("CTRL_V") is True
    assert is_allowed_window_shortcut("CTRL_Z") is True
    assert is_allowed_window_shortcut("CTRL_Y") is False
    assert is_allowed_window_shortcut("ctrl_a") is False
    assert is_allowed_window_shortcut(None) is False
    assert is_destructive_window_shortcut("CTRL_X") is True
    assert is_destructive_window_shortcut("CTRL_Z") is True
    assert is_destructive_window_shortcut("CTRL_A") is False
    assert is_destructive_window_shortcut("CTRL_C") is False
    assert is_privileged_window_shortcut("CTRL_V") is True
    assert is_privileged_window_shortcut("CTRL_A") is False


def test_window_shortcut_risk_sets_do_not_overlap() -> None:
    assert DESTRUCTIVE_WINDOW_SHORTCUTS.isdisjoint(PRIVILEGED_WINDOW_SHORTCUTS)
