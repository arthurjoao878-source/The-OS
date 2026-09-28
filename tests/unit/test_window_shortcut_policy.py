from __future__ import annotations

from theos.core.window_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    is_allowed_window_shortcut,
)


def test_window_shortcut_allowlist_is_exact_and_bounded() -> None:
    assert ALLOWED_WINDOW_SHORTCUTS == ("CTRL_A",)
    assert is_allowed_window_shortcut("CTRL_A") is True
    assert is_allowed_window_shortcut("CTRL_C") is False
    assert is_allowed_window_shortcut("CTRL_V") is False
    assert is_allowed_window_shortcut("ctrl_a") is False
    assert is_allowed_window_shortcut(None) is False
