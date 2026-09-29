from __future__ import annotations

ALLOWED_WINDOW_SHORTCUTS: tuple[str, ...] = (
    "CTRL_A",
    "CTRL_C",
    "CTRL_X",
)

DESTRUCTIVE_WINDOW_SHORTCUTS: frozenset[str] = frozenset(
    {
        "CTRL_X",
    }
)


def is_allowed_window_shortcut(value: object) -> bool:
    return isinstance(value, str) and value in ALLOWED_WINDOW_SHORTCUTS


def is_destructive_window_shortcut(value: object) -> bool:
    return isinstance(value, str) and value in DESTRUCTIVE_WINDOW_SHORTCUTS
