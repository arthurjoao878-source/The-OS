from __future__ import annotations

from theos.core.window_targets import is_window_target_token
from theos.integrations.windows.desktop_windows import _window_target_token


def test_window_target_token_is_opaque_stable_and_handle_specific() -> None:
    first = _window_target_token(101, 4321, "Calculadora")
    same = _window_target_token(101, 4321, "Calculadora")
    other_handle = _window_target_token(202, 4321, "Calculadora")

    assert is_window_target_token(first) is True
    assert first == same
    assert first != other_handle
    assert is_window_target_token(first.upper()) is False
    assert is_window_target_token("a" * 63) is False
