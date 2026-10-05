from __future__ import annotations

import hashlib
import hmac
import secrets

from theos.core.window_targets import is_window_target_token

SEMANTIC_WINDOW_SNAPSHOT_VERSION = 1
MAX_SEMANTIC_CONTROLS = 32
MAX_SEMANTIC_NAME_CHARS = 120
SEMANTIC_CONTROL_TOKEN_CHARS = 64

_SEMANTIC_CONTROL_TOKEN_KEY = secrets.token_bytes(32)


def semantic_role_for_class(class_name: str) -> str:
    normalized = class_name.strip().casefold()
    if not normalized:
        return "unknown"

    if normalized == "button":
        return "button"
    if normalized == "static":
        return "label"
    if normalized == "edit" or normalized.startswith("richedit"):
        return "text_editor"
    if "combobox" in normalized:
        return "combo_box"
    if normalized in {"listbox", "syslistview32"}:
        return "list"
    if normalized == "systreeview32":
        return "tree"
    if normalized == "systabcontrol32":
        return "tab"
    if normalized == "toolbarwindow32":
        return "toolbar"
    if normalized == "msctls_statusbar32":
        return "status_bar"
    if normalized in {"scrollbar", "scrollbarwindow32"}:
        return "scroll_bar"
    return "native_control"


def semantic_name_allowed_for_class(class_name: str) -> bool:
    return semantic_role_for_class(class_name) in {"button", "label"}


def build_semantic_control_token(
    parent_target_token: str,
    *,
    child_hwnd: int,
    pid: int,
    class_name: str,
    control_id: int,
) -> str:
    if not is_window_target_token(parent_target_token):
        raise ValueError("parent_target_token must be a valid window target token")
    if (
        not isinstance(child_hwnd, int)
        or isinstance(child_hwnd, bool)
        or child_hwnd <= 0
    ):
        raise ValueError("child_hwnd must be a positive integer")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("pid must be a positive integer")
    if not isinstance(class_name, str) or not class_name.strip():
        raise ValueError("class_name must be non-blank")
    if not isinstance(control_id, int) or isinstance(control_id, bool):
        raise TypeError("control_id must be an integer")

    payload = (
        f"{SEMANTIC_WINDOW_SNAPSHOT_VERSION}\0"
        f"{parent_target_token}\0"
        f"{child_hwnd}\0"
        f"{pid}\0"
        f"{class_name.strip()}\0"
        f"{control_id}"
    ).encode()

    return hmac.new(
        _SEMANTIC_CONTROL_TOKEN_KEY,
        payload,
        hashlib.sha256,
    ).hexdigest()


def is_semantic_control_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SEMANTIC_CONTROL_TOKEN_CHARS
        and all(character in "0123456789abcdef" for character in value)
    )
