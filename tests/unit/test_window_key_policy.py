from __future__ import annotations

from theos.core.window_keys import ALLOWED_WINDOW_KEYS, is_allowed_window_key


def test_window_key_allowlist_is_exact_and_bounded() -> None:
    assert ALLOWED_WINDOW_KEYS == (
        "ENTER",
        "ESCAPE",
        "TAB",
        "UP",
        "DOWN",
        "LEFT",
        "RIGHT",
        "HOME",
        "END",
        "PAGE_UP",
        "PAGE_DOWN",
        "BACKSPACE",
        "DELETE",
    )
    assert is_allowed_window_key("ENTER") is True
    assert is_allowed_window_key("ESCAPE") is True
    assert is_allowed_window_key("TAB") is True
    assert is_allowed_window_key("UP") is True
    assert is_allowed_window_key("DOWN") is True
    assert is_allowed_window_key("LEFT") is True
    assert is_allowed_window_key("RIGHT") is True
    assert is_allowed_window_key("HOME") is True
    assert is_allowed_window_key("END") is True
    assert is_allowed_window_key("PAGE_UP") is True
    assert is_allowed_window_key("PAGE_DOWN") is True
    assert is_allowed_window_key("BACKSPACE") is True
    assert is_allowed_window_key("DELETE") is True
    assert is_allowed_window_key("F1") is False
    assert is_allowed_window_key("enter") is False
    assert is_allowed_window_key(None) is False
