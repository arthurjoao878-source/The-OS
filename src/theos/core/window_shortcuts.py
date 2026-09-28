from __future__ import annotations

ALLOWED_WINDOW_SHORTCUTS: tuple[str, ...] = (
    "CTRL_A",
    "CTRL_C",
)


def is_allowed_window_shortcut(value: object) -> bool:
    return isinstance(value, str) and value in ALLOWED_WINDOW_SHORTCUTS
