from __future__ import annotations

WINDOW_TARGET_TOKEN_CHARS = 64


def is_window_target_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == WINDOW_TARGET_TOKEN_CHARS
        and all(character in "0123456789abcdef" for character in value)
    )
