from __future__ import annotations

ALLOWED_WINDOW_KEYS: tuple[str, ...] = (
    "ENTER",
    "ESCAPE",
    "TAB",
)


def is_allowed_window_key(value: object) -> bool:
    return isinstance(value, str) and value in ALLOWED_WINDOW_KEYS
