from __future__ import annotations

from theos.core.window_keys import ALLOWED_WINDOW_KEYS, is_allowed_window_key


def test_window_key_allowlist_is_exact_and_bounded() -> None:
    assert ALLOWED_WINDOW_KEYS == ("ENTER", "ESCAPE", "TAB")
    assert is_allowed_window_key("ENTER") is True
    assert is_allowed_window_key("ESCAPE") is True
    assert is_allowed_window_key("TAB") is True
    assert is_allowed_window_key("DELETE") is False
    assert is_allowed_window_key("enter") is False
    assert is_allowed_window_key(None) is False
