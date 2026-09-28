from __future__ import annotations

ALLOWED_WINDOW_KEYS: tuple[str, ...] = (
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

DESTRUCTIVE_WINDOW_KEYS: frozenset[str] = frozenset(
    {
        "BACKSPACE",
        "DELETE",
    }
)


def is_allowed_window_key(value: object) -> bool:
    return isinstance(value, str) and value in ALLOWED_WINDOW_KEYS


def is_destructive_window_key(value: object) -> bool:
    return isinstance(value, str) and value in DESTRUCTIVE_WINDOW_KEYS
