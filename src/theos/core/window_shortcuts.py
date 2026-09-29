from __future__ import annotations

from theos.core.keyboard_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    DESTRUCTIVE_WINDOW_SHORTCUTS,
    PRIVILEGED_WINDOW_SHORTCUTS,
    WINDOW_SHORTCUT_REGISTRY,
    WINDOW_SHORTCUT_SPECS,
    WindowShortcutSpec,
    build_window_shortcut_tool_description,
    format_window_shortcut_allowlist_pt,
    get_window_shortcut_spec,
    is_allowed_window_shortcut,
    is_destructive_window_shortcut,
    is_privileged_window_shortcut,
)

__all__ = [
    "ALLOWED_WINDOW_SHORTCUTS",
    "DESTRUCTIVE_WINDOW_SHORTCUTS",
    "PRIVILEGED_WINDOW_SHORTCUTS",
    "WINDOW_SHORTCUT_REGISTRY",
    "WINDOW_SHORTCUT_SPECS",
    "WindowShortcutSpec",
    "build_window_shortcut_tool_description",
    "format_window_shortcut_allowlist_pt",
    "get_window_shortcut_spec",
    "is_allowed_window_shortcut",
    "is_destructive_window_shortcut",
    "is_privileged_window_shortcut",
]
