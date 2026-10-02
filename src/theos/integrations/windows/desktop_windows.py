from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import secrets
import time
from ctypes import wintypes

import psutil

from theos.core.keyboard_keys import ALLOWED_WINDOW_KEYS
from theos.core.keyboard_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    WINDOW_SHORTCUT_SPECS,
    get_window_shortcut_spec,
)
from theos.core.mouse_anchors import (
    ALLOWED_MOUSE_ANCHORS,
    get_mouse_anchor_spec,
)
from theos.core.mouse_clicks import ALLOWED_MOUSE_BUTTONS
from theos.core.mouse_drags import ALLOWED_MOUSE_DRAGS
from theos.core.mouse_gestures import ALLOWED_MOUSE_GESTURES
from theos.core.mouse_scroll import ALLOWED_MOUSE_SCROLL_DIRECTIONS
from theos.core.window_layout_pairs import (
    HostedWindowCandidate,
    get_window_pair_layout_spec,
    resolve_hosted_visual_frame_for_single_placement,
    resolve_hosted_visual_frame_with_dwm_tiebreak,
)
from theos.core.window_layout_sets import (
    get_window_set_layout_spec,
    resolve_hosted_visual_frame_for_set,
)
from theos.core.window_placements import (
    ALLOWED_WINDOW_PLACEMENTS,
    get_window_placement_spec,
)
from theos.core.window_targets import (
    is_window_target_token,
    normalize_window_queries,
    normalize_window_query,
    window_target_matches_query,
)

MAX_WINDOW_RESULTS = 12
MAX_WINDOW_TITLE_CHARS = 160
FOREGROUND_VERIFY_TIMEOUT_SECONDS = 0.75
FOREGROUND_VERIFY_INTERVAL_SECONDS = 0.05
WINDOW_CLOSE_VERIFY_TIMEOUT_SECONDS = 3.0
WINDOW_CLOSE_VERIFY_INTERVAL_SECONDS = 0.05
WINDOW_MINIMIZE_VERIFY_TIMEOUT_SECONDS = 0.75
WINDOW_MINIMIZE_VERIFY_INTERVAL_SECONDS = 0.05
WINDOW_MAXIMIZE_VERIFY_TIMEOUT_SECONDS = 0.75
WINDOW_MAXIMIZE_VERIFY_INTERVAL_SECONDS = 0.05
WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS = 0.75
WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS = 0.05
MAX_TEXT_INPUT_CHARS = 512
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_PAGE_UP = 0x21
VK_PAGE_DOWN = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
VK_X = 0x58
VK_Z = 0x5A
_WINDOW_KEY_VK_CODES = {
    "ENTER": VK_RETURN,
    "ESCAPE": VK_ESCAPE,
    "TAB": VK_TAB,
    "UP": VK_UP,
    "DOWN": VK_DOWN,
    "LEFT": VK_LEFT,
    "RIGHT": VK_RIGHT,
    "HOME": VK_HOME,
    "END": VK_END,
    "PAGE_UP": VK_PAGE_UP,
    "PAGE_DOWN": VK_PAGE_DOWN,
    "BACKSPACE": VK_BACK,
    "DELETE": VK_DELETE,
}
def _window_shortcut_primary_vk(primary_key: str) -> int:
    if len(primary_key) == 1 and "A" <= primary_key <= "Z":
        return ord(primary_key)

    virtual_key = _WINDOW_KEY_VK_CODES.get(primary_key)
    if virtual_key is None:
        raise RuntimeError(f"SHORTCUT_PRIMARY_KEY_TRANSPORT_MISSING:{primary_key}")
    return virtual_key


_WINDOW_SHORTCUT_VK_PAIRS = {
    spec.name: (VK_CONTROL, _window_shortcut_primary_vk(spec.primary_key))
    for spec in WINDOW_SHORTCUT_SPECS
}
_MOUSE_BUTTON_FLAGS = {
    "LEFT": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "RIGHT": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "MIDDLE": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}
if set(_MOUSE_BUTTON_FLAGS) != set(ALLOWED_MOUSE_BUTTONS):
    raise RuntimeError("MOUSE_BUTTON_TRANSPORT_COVERAGE_MISMATCH")


_MOUSE_GESTURE_FLAGS = {
    "DOUBLE_LEFT": (
        MOUSEEVENTF_LEFTDOWN,
        MOUSEEVENTF_LEFTUP,
        MOUSEEVENTF_LEFTDOWN,
        MOUSEEVENTF_LEFTUP,
    ),
}
if set(_MOUSE_GESTURE_FLAGS) != set(ALLOWED_MOUSE_GESTURES):
    raise RuntimeError("MOUSE_GESTURE_TRANSPORT_COVERAGE_MISMATCH")


_MOUSE_DRAG_FLAGS = {
    "LEFT_DRAG": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
}
if set(_MOUSE_DRAG_FLAGS) != set(ALLOWED_MOUSE_DRAGS):
    raise RuntimeError("MOUSE_DRAG_TRANSPORT_COVERAGE_MISMATCH")


_MOUSE_WHEEL_DELTAS = {
    "UP": WHEEL_DELTA,
    "DOWN": -WHEEL_DELTA,
}
if set(_MOUSE_WHEEL_DELTAS) != set(ALLOWED_MOUSE_SCROLL_DIRECTIONS):
    raise RuntimeError("MOUSE_SCROLL_TRANSPORT_COVERAGE_MISMATCH")


SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
MONITOR_DEFAULTTONEAREST = 2


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060
_WINDOW_TARGET_TOKEN_KEY = secrets.token_bytes(32)


def _window_target_token(hwnd: int, pid: int, bounded_title: str) -> str:
    payload = f"{hwnd}\0{pid}\0{bounded_title}".encode()
    return hmac.new(
        _WINDOW_TARGET_TOKEN_KEY,
        payload,
        hashlib.sha256,
    ).hexdigest()


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [
        ("mi", _MouseInput),
        ("ki", _KeyboardInput),
        ("hi", _HardwareInput),
    ]


class _Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("data", _InputUnion),
    ]


class WindowsDesktopWindowAdapter:
    def snapshot(self, query: str | None = None) -> dict[str, object]:
        normalized_query = None
        if query is not None:
            normalized_query = normalize_window_query(query)
            if normalized_query is None:
                raise RuntimeError("WINDOW_QUERY_INVALID")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        rows: list[dict[str, object]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            title_length = int(user32.GetWindowTextLengthW(hwnd))
            if title_length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(title_length + 1)
            copied = int(
                user32.GetWindowTextW(
                    hwnd,
                    buffer,
                    title_length + 1,
                )
            )
            if copied <= 0:
                return True

            title = buffer.value.strip()
            if not title:
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            pid = int(process_id.value)
            if pid <= 0:
                return True

            try:
                process_name = psutil.Process(pid).name()
            except psutil.Error:
                process_name = "processo-indisponivel"

            bounded_title = title[:MAX_WINDOW_TITLE_CHARS]
            rows.append(
                {
                    "title": bounded_title,
                    "pid": pid,
                    "process_name": process_name,
                    "target_token": _window_target_token(
                        int(hwnd),
                        pid,
                        bounded_title,
                    ),
                }
            )
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        matching_rows = rows
        if normalized_query is not None:
            matching_rows = [
                row
                for row in rows
                if window_target_matches_query(
                    normalized_query,
                    str(row["title"]),
                    str(row["process_name"]),
                )
            ]

        selected = matching_rows[:MAX_WINDOW_RESULTS]
        return {
            "observed_windows": len(rows),
            "matched_windows": len(matching_rows),
            "returned_windows": len(selected),
            "max_results": MAX_WINDOW_RESULTS,
            "max_title_chars": MAX_WINDOW_TITLE_CHARS,
            "filter_applied": normalized_query is not None,
            "filter_query": normalized_query,
            "filter_match": "casefold_substring_title_or_process_name",
            "order": (
                "windows_z_order_within_filter"
                if normalized_query is not None
                else "windows_z_order"
            ),
            "fields": ["title", "pid", "process_name", "target_token"],
            "windows": selected,
        }


    def snapshot_many(
        self,
        queries: tuple[str, ...],
    ) -> dict[str, object]:
        normalized_queries = normalize_window_queries(queries)
        if normalized_queries is None:
            raise RuntimeError("WINDOW_QUERIES_INVALID")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        rows: list[dict[str, object]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            title_length = int(user32.GetWindowTextLengthW(hwnd))
            if title_length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(title_length + 1)
            copied = int(
                user32.GetWindowTextW(
                    hwnd,
                    buffer,
                    title_length + 1,
                )
            )
            if copied <= 0:
                return True

            title = buffer.value.strip()
            if not title:
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            pid = int(process_id.value)
            if pid <= 0:
                return True

            try:
                process_name = psutil.Process(pid).name()
            except psutil.Error:
                process_name = "processo-indisponivel"

            bounded_title = title[:MAX_WINDOW_TITLE_CHARS]
            rows.append(
                {
                    "title": bounded_title,
                    "pid": pid,
                    "process_name": process_name,
                    "target_token": _window_target_token(
                        int(hwnd),
                        pid,
                        bounded_title,
                    ),
                }
            )
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        query_match_counts = {
            query: 0
            for query in normalized_queries
        }
        matching_rows: list[dict[str, object]] = []
        for row in rows:
            matched_any = False
            for query in normalized_queries:
                if window_target_matches_query(
                    query,
                    str(row["title"]),
                    str(row["process_name"]),
                ):
                    query_match_counts[query] += 1
                    matched_any = True
            if matched_any:
                matching_rows.append(row)

        selected = matching_rows[:MAX_WINDOW_RESULTS]
        return {
            "observed_windows": len(rows),
            "matched_windows": len(matching_rows),
            "returned_windows": len(selected),
            "max_results": MAX_WINDOW_RESULTS,
            "max_title_chars": MAX_WINDOW_TITLE_CHARS,
            "filter_applied": True,
            "filter_queries": list(normalized_queries),
            "filter_count": len(normalized_queries),
            "filter_mode": "any_query",
            "filter_match": "casefold_substring_title_or_process_name",
            "query_match_counts": query_match_counts,
            "order": "windows_z_order_within_multi_filter",
            "fields": ["title", "pid", "process_name", "target_token"],
            "windows": selected,
        }


    def _enumerate_action_window_candidates(
        self,
        user32: object,
        callback_type: object,
    ) -> tuple[
        tuple[HostedWindowCandidate, ...],
        dict[int, str],
        dict[int, int | None],
        frozenset[int],
    ]:
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.IsZoomed.argtypes = [wintypes.HWND]
        user32.IsZoomed.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL

        dwmapi = None
        try:
            dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        except OSError:
            pass

        if dwmapi is not None:
            dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
            ]
            dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

        def get_dwm_cloaked(hwnd: wintypes.HWND) -> int | None:
            if dwmapi is None:
                return None
            value = wintypes.DWORD()
            result = int(
                dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    14,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            )
            if result != 0:
                return None
            return int(value.value)

        candidates: list[HostedWindowCandidate] = []
        full_titles: dict[int, str] = {}
        dwm_cloaked_by_hwnd: dict[int, int | None] = {}
        visible_pids: set[int] = set()

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            candidate_pid = int(process_id.value)
            if candidate_pid <= 0:
                return True
            visible_pids.add(candidate_pid)

            title_length = int(user32.GetWindowTextLengthW(hwnd))
            if title_length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(title_length + 1)
            copied = int(
                user32.GetWindowTextW(hwnd, buffer, title_length + 1)
            )
            if copied <= 0:
                return True

            full_title = buffer.value.strip()
            if not full_title:
                return True
            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]

            candidate_token = _window_target_token(
                int(hwnd),
                candidate_pid,
                bounded_title,
            )

            class_buffer = ctypes.create_unicode_buffer(256)
            class_length = int(
                user32.GetClassNameW(
                    hwnd,
                    class_buffer,
                    len(class_buffer),
                )
            )
            class_name = class_buffer.value if class_length > 0 else ""

            client_rect = wintypes.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
                client_width = int(client_rect.right - client_rect.left)
                client_height = int(client_rect.bottom - client_rect.top)
            else:
                client_width = 0
                client_height = 0

            hwnd_value = int(hwnd)
            full_titles[hwnd_value] = full_title
            dwm_cloaked_by_hwnd[hwnd_value] = get_dwm_cloaked(hwnd)
            candidates.append(
                HostedWindowCandidate(
                    hwnd=hwnd_value,
                    pid=candidate_pid,
                    title=bounded_title,
                    target_token=candidate_token,
                    class_name=class_name,
                    is_iconic=bool(user32.IsIconic(hwnd)),
                    is_zoomed=bool(user32.IsZoomed(hwnd)),
                    client_width=client_width,
                    client_height=client_height,
                )
            )
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            raise OSError(ctypes.get_last_error(), "EnumWindows failed")

        return (
            tuple(candidates),
            full_titles,
            dwm_cloaked_by_hwnd,
            frozenset(visible_pids),
        )

    def _resolve_exact_window_target(
        self,
        user32: object,
        callback_type: object,
        pid: int,
        title: str,
        target_token: str,
        *,
        stale_detail: bool = False,
    ) -> tuple[
        HostedWindowCandidate,
        HostedWindowCandidate,
        str,
        str,
        bool,
        bool,
        int | None,
    ]:
        (
            all_candidates,
            full_titles,
            dwm_cloaked_by_hwnd,
            visible_pids,
        ) = self._enumerate_action_window_candidates(
            user32,
            callback_type,
        )

        visible_pid_matches = pid in visible_pids
        visible_pid_title_matches = any(
            candidate.pid == pid and candidate.title == title
            for candidate in all_candidates
        )

        matches = [
            candidate
            for candidate in all_candidates
            if candidate.pid == pid
            and candidate.title == title
            and candidate.target_token == target_token
        ]
        if not matches:
            if stale_detail and visible_pid_title_matches:
                raise RuntimeError("WINDOW_TARGET_TOKEN_STALE")
            if stale_detail and visible_pid_matches:
                raise RuntimeError("WINDOW_TARGET_TITLE_CHANGED")
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        requested = matches[0]
        try:
            resolved, normalized, dwm_tiebreak_used = (
                resolve_hosted_visual_frame_for_single_placement(
                    requested,
                    all_candidates,
                    dwm_cloaked_by_hwnd,
                )
            )
        except ValueError as exc:
            if str(exc) == "HOSTED_VISUAL_FRAME_NOT_FOUND":
                raise RuntimeError("WINDOW_VISUAL_FRAME_NOT_FOUND") from exc
            if str(exc) == "HOSTED_VISUAL_FRAME_AMBIGUOUS":
                raise RuntimeError("WINDOW_VISUAL_FRAME_AMBIGUOUS") from exc
            raise

        return (
            requested,
            resolved,
            full_titles[requested.hwnd],
            full_titles[resolved.hwnd],
            normalized,
            dwm_tiebreak_used,
            dwm_cloaked_by_hwnd.get(resolved.hwnd),
        )


    def activate_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified = False
        while time.monotonic() <= deadline:
            foreground = user32.GetForegroundWindow()
            if foreground and int(foreground) == hwnd_value:
                foreground_verified = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified:
            raise RuntimeError("WINDOW_FOREGROUND_NOT_VERIFIED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "activated": True,
            "foreground_verified": True,
            "restored_from_minimized": was_minimized,
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_process_name": resolved_process_name,
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def click_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        button: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_INPUT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if button not in ALLOWED_MOUSE_BUTTONS:
            raise RuntimeError("MOUSE_INPUT_NOT_ALLOWED")
        down_flag, up_flag = _MOUSE_BUTTON_FLAGS[button]

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError("MOUSE_INPUT_TARGET_ACTIVATION_NOT_VERIFIED")

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("MOUSE_INPUT_WINDOW_RECT_INVALID")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise RuntimeError("MOUSE_INPUT_WINDOW_RECT_INVALID")

        click_x = int((rect.left + rect.right) // 2)
        click_y = int((rect.top + rect.bottom) // 2)

        if not user32.SetCursorPos(click_x, click_y):
            raise RuntimeError("MOUSE_CURSOR_POSITION_NOT_VERIFIED")

        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError("MOUSE_CURSOR_POSITION_NOT_VERIFIED")
        if int(cursor.x) != click_x or int(cursor.y) != click_y:
            raise RuntimeError("MOUSE_CURSOR_POSITION_NOT_VERIFIED")

        events = (
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=down_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=up_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            release_event = _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=up_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            release_array_type = _Input * 1
            release_array = release_array_type(release_event)
            user32.SendInput(
                1,
                release_array,
                ctypes.sizeof(_Input),
            )
            raise RuntimeError("MOUSE_INPUT_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_INPUT_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "button": button,
            "position_mode": "window_center",
            "click_screen_x": click_x,
            "click_screen_y": click_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "window_center_cursor_sendinput_count_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{button}",
            "button_allowlist": list(ALLOWED_MOUSE_BUTTONS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def move_cursor_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        anchor: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_MOVE_ANCHOR_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        anchor_spec = get_mouse_anchor_spec(anchor)
        if anchor_spec is None:
            raise RuntimeError("MOUSE_MOVE_ANCHOR_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        ]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)
        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)
        if not foreground_verified_before:
            raise RuntimeError(
                "MOUSE_MOVE_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED"
            )

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            raise RuntimeError("MOUSE_MOVE_ANCHOR_CLIENT_RECT_INVALID")
        client_width = int(client_rect.right - client_rect.left)
        client_height = int(client_rect.bottom - client_rect.top)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError("MOUSE_MOVE_ANCHOR_CLIENT_RECT_INVALID")

        client_origin = wintypes.POINT(
            x=int(client_rect.left),
            y=int(client_rect.top),
        )
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            raise RuntimeError(
                "MOUSE_MOVE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED"
            )

        cursor_x = int(
            client_origin.x + (client_width * anchor_spec.x_percent) // 100
        )
        cursor_y = int(
            client_origin.y + (client_height * anchor_spec.y_percent) // 100
        )

        if not user32.SetCursorPos(cursor_x, cursor_y):
            raise RuntimeError(
                "MOUSE_MOVE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )
        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError(
                "MOUSE_MOVE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )
        if int(cursor.x) != cursor_x or int(cursor.y) != cursor_y:
            raise RuntimeError(
                "MOUSE_MOVE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_MOVE_ANCHOR_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "anchor": anchor,
            "anchor_label_pt": anchor_spec.label_pt,
            "anchor_x_percent": anchor_spec.x_percent,
            "anchor_y_percent": anchor_spec.y_percent,
            "position_mode": "client_anchor",
            "client_width": client_width,
            "client_height": client_height,
            "cursor_screen_x": cursor_x,
            "cursor_screen_y": cursor_y,
            "cursor_position_verified": True,
            "input_events_submitted": 0,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "cursor_move_verified": True,
            "hover_effect_verified": False,
            "content_effect_verified": False,
            "verification": "client_anchor_cursor_position_and_foreground_only",
            "input_method": "SetCursorPos_ONLY",
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def scroll_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        direction: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_SCROLL_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if direction not in ALLOWED_MOUSE_SCROLL_DIRECTIONS:
            raise RuntimeError("MOUSE_SCROLL_NOT_ALLOWED")
        wheel_delta = _MOUSE_WHEEL_DELTAS[direction]

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError("MOUSE_SCROLL_TARGET_ACTIVATION_NOT_VERIFIED")

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("MOUSE_SCROLL_WINDOW_RECT_INVALID")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise RuntimeError("MOUSE_SCROLL_WINDOW_RECT_INVALID")

        cursor_x = int((rect.left + rect.right) // 2)
        cursor_y = int((rect.top + rect.bottom) // 2)

        if not user32.SetCursorPos(cursor_x, cursor_y):
            raise RuntimeError("MOUSE_SCROLL_CURSOR_POSITION_NOT_VERIFIED")

        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError("MOUSE_SCROLL_CURSOR_POSITION_NOT_VERIFIED")
        if int(cursor.x) != cursor_x or int(cursor.y) != cursor_y:
            raise RuntimeError("MOUSE_SCROLL_CURSOR_POSITION_NOT_VERIFIED")

        event = _Input(
            type=INPUT_MOUSE,
            data=_InputUnion(
                mi=_MouseInput(
                    dx=0,
                    dy=0,
                    mouseData=wheel_delta & 0xFFFFFFFF,
                    dwFlags=MOUSEEVENTF_WHEEL,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        event_array_type = _Input * 1
        event_array = event_array_type(event)
        submitted = int(
            user32.SendInput(
                1,
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != 1:
            raise RuntimeError("MOUSE_SCROLL_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_SCROLL_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "direction": direction,
            "position_mode": "window_center",
            "scroll_units": 1,
            "wheel_delta": wheel_delta,
            "cursor_screen_x": cursor_x,
            "cursor_screen_y": cursor_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "window_center_cursor_wheel_sendinput_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_WHEEL_{direction}",
            "direction_allowlist": list(ALLOWED_MOUSE_SCROLL_DIRECTIONS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def click_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        button: str,
        anchor: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_ANCHOR_INPUT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if button not in ALLOWED_MOUSE_BUTTONS:
            raise RuntimeError("MOUSE_ANCHOR_INPUT_NOT_ALLOWED")
        anchor_spec = get_mouse_anchor_spec(anchor)
        if anchor_spec is None:
            raise RuntimeError("MOUSE_ANCHOR_INPUT_NOT_ALLOWED")
        down_flag, up_flag = _MOUSE_BUTTON_FLAGS[button]

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        ]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError(
                "MOUSE_ANCHOR_INPUT_TARGET_ACTIVATION_NOT_VERIFIED"
            )

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            raise RuntimeError("MOUSE_ANCHOR_CLIENT_RECT_INVALID")
        client_width = int(client_rect.right - client_rect.left)
        client_height = int(client_rect.bottom - client_rect.top)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError("MOUSE_ANCHOR_CLIENT_RECT_INVALID")

        client_origin = wintypes.POINT(
            x=int(client_rect.left),
            y=int(client_rect.top),
        )
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            raise RuntimeError("MOUSE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED")

        click_x = int(
            client_origin.x
            + (client_width * anchor_spec.x_percent) // 100
        )
        click_y = int(
            client_origin.y
            + (client_height * anchor_spec.y_percent) // 100
        )

        if not user32.SetCursorPos(click_x, click_y):
            raise RuntimeError("MOUSE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED")

        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError("MOUSE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED")
        if int(cursor.x) != click_x or int(cursor.y) != click_y:
            raise RuntimeError("MOUSE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED")

        events = (
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=down_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=up_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            release_event = _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=up_flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            release_array_type = _Input * 1
            release_array = release_array_type(release_event)
            user32.SendInput(
                1,
                release_array,
                ctypes.sizeof(_Input),
            )
            raise RuntimeError("MOUSE_ANCHOR_INPUT_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_ANCHOR_INPUT_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "button": button,
            "anchor": anchor,
            "anchor_label_pt": anchor_spec.label_pt,
            "anchor_x_percent": anchor_spec.x_percent,
            "anchor_y_percent": anchor_spec.y_percent,
            "position_mode": "client_anchor",
            "client_width": client_width,
            "client_height": client_height,
            "click_screen_x": click_x,
            "click_screen_y": click_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_cursor_sendinput_count_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{button}_ANCHOR_{anchor}",
            "button_allowlist": list(ALLOWED_MOUSE_BUTTONS),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def double_click_window_center(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_DOUBLE_CLICK_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        flags = _MOUSE_GESTURE_FLAGS.get(gesture)
        if flags is None:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_TARGET_ACTIVATION_NOT_VERIFIED"
            )

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("MOUSE_DOUBLE_CLICK_WINDOW_RECT_INVALID")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_WINDOW_RECT_INVALID")

        click_x = int((rect.left + rect.right) // 2)
        click_y = int((rect.top + rect.bottom) // 2)

        if not user32.SetCursorPos(click_x, click_y):
            raise RuntimeError("MOUSE_DOUBLE_CLICK_CURSOR_POSITION_NOT_VERIFIED")

        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError("MOUSE_DOUBLE_CLICK_CURSOR_POSITION_NOT_VERIFIED")
        if int(cursor.x) != click_x or int(cursor.y) != click_y:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_CURSOR_POSITION_NOT_VERIFIED")

        events = tuple(
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            for flag in flags
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            release_event = _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=MOUSEEVENTF_LEFTUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            release_array_type = _Input * 1
            release_array = release_array_type(release_event)
            user32.SendInput(
                1,
                release_array,
                ctypes.sizeof(_Input),
            )
            raise RuntimeError("MOUSE_DOUBLE_CLICK_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "gesture": gesture,
            "position_mode": "window_center",
            "click_screen_x": click_x,
            "click_screen_y": click_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "semantic_double_click_verified": False,
            "content_effect_verified": False,
            "verification": (
                "window_center_cursor_four_event_sequence_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{gesture}",
            "gesture_allowlist": list(ALLOWED_MOUSE_GESTURES),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def double_click_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
        anchor: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_DOUBLE_CLICK_ANCHOR_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        flags = _MOUSE_GESTURE_FLAGS.get(gesture)
        anchor_spec = get_mouse_anchor_spec(anchor)
        if flags is None or anchor_spec is None:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        ]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED"
            )

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            raise RuntimeError("MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_RECT_INVALID")
        client_width = int(client_rect.right - client_rect.left)
        client_height = int(client_rect.bottom - client_rect.top)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_RECT_INVALID")

        client_origin = wintypes.POINT(
            x=int(client_rect.left),
            y=int(client_rect.top),
        )
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED"
            )

        click_x = int(
            client_origin.x
            + (client_width * anchor_spec.x_percent) // 100
        )
        click_y = int(
            client_origin.y
            + (client_height * anchor_spec.y_percent) // 100
        )

        if not user32.SetCursorPos(click_x, click_y):
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )

        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )
        if int(cursor.x) != click_x or int(cursor.y) != click_y:
            raise RuntimeError(
                "MOUSE_DOUBLE_CLICK_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )

        events = tuple(
            _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            for flag in flags
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            release_event = _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=MOUSEEVENTF_LEFTUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            release_array_type = _Input * 1
            release_array = release_array_type(release_event)
            user32.SendInput(
                1,
                release_array,
                ctypes.sizeof(_Input),
            )
            raise RuntimeError("MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_DOUBLE_CLICK_ANCHOR_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "gesture": gesture,
            "anchor": anchor,
            "anchor_label_pt": anchor_spec.label_pt,
            "anchor_x_percent": anchor_spec.x_percent,
            "anchor_y_percent": anchor_spec.y_percent,
            "position_mode": "client_anchor",
            "client_width": client_width,
            "client_height": client_height,
            "click_screen_x": click_x,
            "click_screen_y": click_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "semantic_double_click_verified": False,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_cursor_four_event_sequence_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_{gesture}_ANCHOR_{anchor}",
            "gesture_allowlist": list(ALLOWED_MOUSE_GESTURES),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def drag_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        gesture: str,
        source_anchor: str,
        target_anchor: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_DRAG_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        flags = _MOUSE_DRAG_FLAGS.get(gesture)
        source_spec = get_mouse_anchor_spec(source_anchor)
        target_spec = get_mouse_anchor_spec(target_anchor)
        if (
            flags is None
            or source_spec is None
            or target_spec is None
            or source_anchor == target_anchor
        ):
            raise RuntimeError("MOUSE_DRAG_NOT_ALLOWED")
        down_flag, up_flag = flags

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        ]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)
        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)
        if not foreground_verified_before:
            raise RuntimeError("MOUSE_DRAG_TARGET_ACTIVATION_NOT_VERIFIED")

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            raise RuntimeError("MOUSE_DRAG_CLIENT_RECT_INVALID")
        client_width = int(client_rect.right - client_rect.left)
        client_height = int(client_rect.bottom - client_rect.top)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError("MOUSE_DRAG_CLIENT_RECT_INVALID")

        client_origin = wintypes.POINT(
            x=int(client_rect.left),
            y=int(client_rect.top),
        )
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            raise RuntimeError("MOUSE_DRAG_CLIENT_ORIGIN_NOT_VERIFIED")

        source_x = int(
            client_origin.x + (client_width * source_spec.x_percent) // 100
        )
        source_y = int(
            client_origin.y + (client_height * source_spec.y_percent) // 100
        )
        target_x = int(
            client_origin.x + (client_width * target_spec.x_percent) // 100
        )
        target_y = int(
            client_origin.y + (client_height * target_spec.y_percent) // 100
        )

        if not user32.SetCursorPos(source_x, source_y):
            raise RuntimeError("MOUSE_DRAG_SOURCE_CURSOR_NOT_VERIFIED")
        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError("MOUSE_DRAG_SOURCE_CURSOR_NOT_VERIFIED")
        if int(cursor.x) != source_x or int(cursor.y) != source_y:
            raise RuntimeError("MOUSE_DRAG_SOURCE_CURSOR_NOT_VERIFIED")

        def submit_single(flag: int) -> int:
            event = _Input(
                type=INPUT_MOUSE,
                data=_InputUnion(
                    mi=_MouseInput(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=flag,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            )
            event_array_type = _Input * 1
            event_array = event_array_type(event)
            return int(
                user32.SendInput(
                    1,
                    event_array,
                    ctypes.sizeof(_Input),
                )
            )

        down_submitted = submit_single(down_flag)
        if down_submitted != 1:
            submit_single(up_flag)
            raise RuntimeError("MOUSE_DRAG_BUTTON_DOWN_NOT_ACCEPTED")

        button_is_down = True
        try:
            foreground_during = user32.GetForegroundWindow()
            if not foreground_during or int(foreground_during) != hwnd_value:
                raise RuntimeError("MOUSE_DRAG_FOREGROUND_CHANGED")

            if not user32.SetCursorPos(target_x, target_y):
                raise RuntimeError("MOUSE_DRAG_TARGET_CURSOR_NOT_VERIFIED")
            target_cursor = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(target_cursor)):
                raise RuntimeError("MOUSE_DRAG_TARGET_CURSOR_NOT_VERIFIED")
            if (
                int(target_cursor.x) != target_x
                or int(target_cursor.y) != target_y
            ):
                raise RuntimeError("MOUSE_DRAG_TARGET_CURSOR_NOT_VERIFIED")

            foreground_before_release = user32.GetForegroundWindow()
            if (
                not foreground_before_release
                or int(foreground_before_release) != hwnd_value
            ):
                raise RuntimeError("MOUSE_DRAG_FOREGROUND_CHANGED")

            up_submitted = submit_single(up_flag)
            button_is_down = False
            if up_submitted != 1:
                submit_single(up_flag)
                raise RuntimeError("MOUSE_DRAG_BUTTON_UP_NOT_ACCEPTED")
        except BaseException:
            if button_is_down:
                submit_single(up_flag)
            raise

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_DRAG_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "gesture": gesture,
            "source_anchor": source_anchor,
            "source_anchor_label_pt": source_spec.label_pt,
            "source_anchor_x_percent": source_spec.x_percent,
            "source_anchor_y_percent": source_spec.y_percent,
            "target_anchor": target_anchor,
            "target_anchor_label_pt": target_spec.label_pt,
            "target_anchor_x_percent": target_spec.x_percent,
            "target_anchor_y_percent": target_spec.y_percent,
            "position_mode": "client_anchor_to_anchor",
            "client_width": client_width,
            "client_height": client_height,
            "source_screen_x": source_x,
            "source_screen_y": source_y,
            "target_screen_x": target_x,
            "target_screen_y": target_y,
            "source_cursor_position_verified": True,
            "target_cursor_position_verified": True,
            "button_down_events_submitted": down_submitted,
            "button_up_events_submitted": up_submitted,
            "input_events_submitted": down_submitted + up_submitted,
            "foreground_verified_before": True,
            "foreground_verified_during": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "semantic_drag_verified": False,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_source_target_cursor_leftdown_leftup_foreground_only"
            ),
            "input_method": "SendInput_MOUSE_LEFT_DRAG_ANCHOR_TO_ANCHOR",
            "gesture_allowlist": list(ALLOWED_MOUSE_DRAGS),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def scroll_window_anchor(
        self,
        pid: int,
        title: str,
        target_token: str,
        direction: str,
        anchor: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MOUSE_SCROLL_ANCHOR_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        wheel_delta = _MOUSE_WHEEL_DELTAS.get(direction)
        anchor_spec = get_mouse_anchor_spec(anchor)
        if wheel_delta is None or anchor_spec is None:
            raise RuntimeError("MOUSE_SCROLL_ANCHOR_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        ]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)
        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)
        if not foreground_verified_before:
            raise RuntimeError(
                "MOUSE_SCROLL_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED"
            )

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            raise RuntimeError("MOUSE_SCROLL_ANCHOR_CLIENT_RECT_INVALID")
        client_width = int(client_rect.right - client_rect.left)
        client_height = int(client_rect.bottom - client_rect.top)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError("MOUSE_SCROLL_ANCHOR_CLIENT_RECT_INVALID")

        client_origin = wintypes.POINT(
            x=int(client_rect.left),
            y=int(client_rect.top),
        )
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            raise RuntimeError(
                "MOUSE_SCROLL_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED"
            )

        cursor_x = int(
            client_origin.x + (client_width * anchor_spec.x_percent) // 100
        )
        cursor_y = int(
            client_origin.y + (client_height * anchor_spec.y_percent) // 100
        )

        if not user32.SetCursorPos(cursor_x, cursor_y):
            raise RuntimeError(
                "MOUSE_SCROLL_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )
        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise RuntimeError(
                "MOUSE_SCROLL_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )
        if int(cursor.x) != cursor_x or int(cursor.y) != cursor_y:
            raise RuntimeError(
                "MOUSE_SCROLL_ANCHOR_CURSOR_POSITION_NOT_VERIFIED"
            )

        event = _Input(
            type=INPUT_MOUSE,
            data=_InputUnion(
                mi=_MouseInput(
                    dx=0,
                    dy=0,
                    mouseData=wheel_delta & 0xFFFFFFFF,
                    dwFlags=MOUSEEVENTF_WHEEL,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        event_array_type = _Input * 1
        event_array = event_array_type(event)
        submitted = int(
            user32.SendInput(
                1,
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != 1:
            raise RuntimeError("MOUSE_SCROLL_ANCHOR_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("MOUSE_SCROLL_ANCHOR_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "direction": direction,
            "anchor": anchor,
            "anchor_label_pt": anchor_spec.label_pt,
            "anchor_x_percent": anchor_spec.x_percent,
            "anchor_y_percent": anchor_spec.y_percent,
            "position_mode": "client_anchor",
            "scroll_units": 1,
            "wheel_delta": wheel_delta,
            "client_width": client_width,
            "client_height": client_height,
            "cursor_screen_x": cursor_x,
            "cursor_screen_y": cursor_y,
            "cursor_position_verified": True,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": (
                "client_anchor_cursor_wheel_sendinput_and_foreground_only"
            ),
            "input_method": f"SendInput_MOUSE_WHEEL_{direction}_ANCHOR_{anchor}",
            "direction_allowlist": list(ALLOWED_MOUSE_SCROLL_DIRECTIONS),
            "anchor_allowlist": list(ALLOWED_MOUSE_ANCHORS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def press_key(
        self,
        pid: int,
        title: str,
        target_token: str,
        key: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_KEY_INPUT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if key not in ALLOWED_WINDOW_KEYS:
            raise RuntimeError("KEY_INPUT_NOT_ALLOWED")
        virtual_key = _WINDOW_KEY_VK_CODES[key]
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError("KEY_INPUT_TARGET_ACTIVATION_NOT_VERIFIED")

        events = (
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=virtual_key,
                        wScan=0,
                        dwFlags=0,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=virtual_key,
                        wScan=0,
                        dwFlags=KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            raise RuntimeError("KEY_INPUT_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("KEY_INPUT_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "key": key,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": f"SendInput_VK_{key}",
            "clipboard_used": False,
            "key_allowlist": list(ALLOWED_WINDOW_KEYS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }


    def press_shortcut(
        self,
        pid: int,
        title: str,
        target_token: str,
        shortcut: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_SHORTCUT_INPUT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")

        shortcut_spec = get_window_shortcut_spec(shortcut)
        if shortcut_spec is None:
            raise RuntimeError("SHORTCUT_INPUT_NOT_ALLOWED")

        modifier_key, primary_key = _WINDOW_SHORTCUT_VK_PAIRS[shortcut]
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError("SHORTCUT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED")

        events = (
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=modifier_key,
                        wScan=0,
                        dwFlags=0,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=primary_key,
                        wScan=0,
                        dwFlags=0,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=primary_key,
                        wScan=0,
                        dwFlags=KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
            _Input(
                type=INPUT_KEYBOARD,
                data=_InputUnion(
                    ki=_KeyboardInput(
                        wVk=modifier_key,
                        wScan=0,
                        dwFlags=KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=0,
                    )
                ),
            ),
        )
        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )

        if submitted != len(events):
            release_events = (
                _Input(
                    type=INPUT_KEYBOARD,
                    data=_InputUnion(
                        ki=_KeyboardInput(
                            wVk=primary_key,
                            wScan=0,
                            dwFlags=KEYEVENTF_KEYUP,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                ),
                _Input(
                    type=INPUT_KEYBOARD,
                    data=_InputUnion(
                        ki=_KeyboardInput(
                            wVk=modifier_key,
                            wScan=0,
                            dwFlags=KEYEVENTF_KEYUP,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                ),
            )
            release_array_type = _Input * len(release_events)
            release_array = release_array_type(*release_events)
            user32.SendInput(
                len(release_events),
                release_array,
                ctypes.sizeof(_Input),
            )
            raise RuntimeError("SHORTCUT_INPUT_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("SHORTCUT_INPUT_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "shortcut": shortcut,
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": f"SendInput_{shortcut}",
            "clipboard_used": shortcut_spec.clipboard_used,
            "clipboard_api_used_by_theos": False,
            "clipboard_effect_expected": shortcut_spec.clipboard_effect_expected,
            "clipboard_effect_verified": False,
            "clipboard_input_expected": shortcut_spec.clipboard_input_expected,
            "clipboard_content_inspected_by_theos": False,
            "clipboard_content_provider_visible": False,
            "content_mutation_expected": shortcut_spec.content_mutation_expected,
            "shortcut_allowlist": list(ALLOWED_WINDOW_SHORTCUTS),
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def type_text(
        self,
        pid: int,
        title: str,
        target_token: str,
        text: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_TEXT_INPUT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not text or len(text) > MAX_TEXT_INPUT_CHARS:
            raise RuntimeError("TEXT_INPUT_INVALID")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
            raise RuntimeError("TEXT_INPUT_CONTROL_CHAR_BLOCKED")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise RuntimeError("TEXT_INPUT_INVALID_UNICODE")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_Input),
            ctypes.c_int,
        ]
        user32.SendInput.restype = wintypes.UINT

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        hwnd_value = resolved_candidate.hwnd
        hwnd = wintypes.HWND(hwnd_value)

        foreground = user32.GetForegroundWindow()
        already_foreground = bool(foreground and int(foreground) == hwnd_value)
        was_minimized = bool(user32.IsIconic(hwnd))
        if was_minimized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        if not already_foreground:
            user32.SetForegroundWindow(hwnd)

        deadline = time.monotonic() + FOREGROUND_VERIFY_TIMEOUT_SECONDS
        foreground_verified_before = False
        while time.monotonic() <= deadline:
            current_foreground = user32.GetForegroundWindow()
            if current_foreground and int(current_foreground) == hwnd_value:
                foreground_verified_before = True
                break
            time.sleep(FOREGROUND_VERIFY_INTERVAL_SECONDS)

        if not foreground_verified_before:
            raise RuntimeError("TEXT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED")

        try:
            utf16 = text.encode("utf-16-le", errors="strict")
        except UnicodeEncodeError as exc:
            raise RuntimeError("TEXT_INPUT_INVALID_UNICODE") from exc

        units = [
            int.from_bytes(utf16[index : index + 2], "little")
            for index in range(0, len(utf16), 2)
        ]
        events: list[_Input] = []
        for unit in units:
            events.append(
                _Input(
                    type=INPUT_KEYBOARD,
                    data=_InputUnion(
                        ki=_KeyboardInput(
                            wVk=0,
                            wScan=unit,
                            dwFlags=KEYEVENTF_UNICODE,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                )
            )
            events.append(
                _Input(
                    type=INPUT_KEYBOARD,
                    data=_InputUnion(
                        ki=_KeyboardInput(
                            wVk=0,
                            wScan=unit,
                            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                )
            )

        event_array_type = _Input * len(events)
        event_array = event_array_type(*events)
        submitted = int(
            user32.SendInput(
                len(events),
                event_array,
                ctypes.sizeof(_Input),
            )
        )
        if submitted != len(events):
            raise RuntimeError("TEXT_INPUT_NOT_ACCEPTED")

        foreground_after = user32.GetForegroundWindow()
        if not foreground_after or int(foreground_after) != hwnd_value:
            raise RuntimeError("TEXT_INPUT_FOREGROUND_CHANGED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "text_chars": len(text),
            "utf16_units": len(units),
            "input_events_submitted": submitted,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": not already_foreground,
            "restored_from_minimized": was_minimized,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": "SendInput_KEYEVENTF_UNICODE",
            "clipboard_used": False,
            "special_keys_used": False,
            "control_characters_allowed": False,
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_candidate.pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def place_window(
        self,
        pid: int,
        title: str,
        target_token: str,
        placement: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_PLACEMENT_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        placement_spec = get_window_placement_spec(placement)
        if placement_spec is None:
            raise RuntimeError("WINDOW_PLACEMENT_NOT_ALLOWED")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        try:
            (
                _requested_candidate,
                resolved_candidate,
                _requested_full_title,
                full_title,
                visual_frame_normalized,
                visual_frame_dwm_tiebreak_used,
                resolved_dwm_cloaked,
            ) = self._resolve_exact_window_target(
                user32,
                callback_type,
                pid,
                title,
                target_token,
            )
        except RuntimeError as exc:
            if str(exc) == "WINDOW_VISUAL_FRAME_NOT_FOUND":
                raise RuntimeError(
                    "WINDOW_PLACEMENT_VISUAL_FRAME_NOT_FOUND"
                ) from exc
            if str(exc) == "WINDOW_VISUAL_FRAME_AMBIGUOUS":
                raise RuntimeError(
                    "WINDOW_PLACEMENT_VISUAL_FRAME_AMBIGUOUS"
                ) from exc
            raise

        if resolved_candidate.pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_PLACEMENT_BLOCKED")

        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_MonitorInfo),
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.MoveWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.BOOL,
        ]
        user32.MoveWindow.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        was_minimized = bool(user32.IsIconic(hwnd))
        was_maximized = bool(user32.IsZoomed(hwnd))
        restored_to_normal = False

        if was_minimized or was_maximized:
            user32.ShowWindow(hwnd, SW_RESTORE)
            deadline = time.monotonic() + WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS
            while time.monotonic() <= deadline:
                if not user32.IsIconic(hwnd) and not user32.IsZoomed(hwnd):
                    restored_to_normal = True
                    break
                time.sleep(WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS)
            if not restored_to_normal:
                raise RuntimeError("WINDOW_PLACEMENT_RESTORE_NOT_VERIFIED")

        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            raise RuntimeError("WINDOW_PLACEMENT_MONITOR_NOT_FOUND")

        monitor_info = _MonitorInfo()
        monitor_info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(
            monitor,
            ctypes.byref(monitor_info),
        ):
            raise RuntimeError("WINDOW_PLACEMENT_MONITOR_INFO_FAILED")

        work = monitor_info.rcWork
        work_left = int(work.left)
        work_top = int(work.top)
        work_right = int(work.right)
        work_bottom = int(work.bottom)
        work_width = work_right - work_left
        work_height = work_bottom - work_top
        if work_width <= 0 or work_height <= 0:
            raise RuntimeError("WINDOW_PLACEMENT_WORK_AREA_INVALID")

        x_start = (
            work_width * placement_spec.x_percent
        ) // 100
        y_start = (
            work_height * placement_spec.y_percent
        ) // 100
        x_end = (
            work_width
            * (placement_spec.x_percent + placement_spec.width_percent)
        ) // 100
        y_end = (
            work_height
            * (placement_spec.y_percent + placement_spec.height_percent)
        ) // 100

        target_left = work_left + x_start
        target_top = work_top + y_start
        target_right = work_left + x_end
        target_bottom = work_top + y_end
        target_width = target_right - target_left
        target_height = target_bottom - target_top
        if target_width <= 0 or target_height <= 0:
            raise RuntimeError("WINDOW_PLACEMENT_WORK_AREA_INVALID")

        if not user32.MoveWindow(
            hwnd,
            target_left,
            target_top,
            target_width,
            target_height,
            True,
        ):
            raise RuntimeError("WINDOW_PLACEMENT_MOVE_NOT_ACCEPTED")

        deadline = time.monotonic() + WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS
        window_rect_verified = False
        final_rect = wintypes.RECT()
        while time.monotonic() <= deadline:
            if (
                user32.GetWindowRect(hwnd, ctypes.byref(final_rect))
                and int(final_rect.left) == target_left
                and int(final_rect.top) == target_top
                and int(final_rect.right) == target_right
                and int(final_rect.bottom) == target_bottom
            ):
                window_rect_verified = True
                break
            time.sleep(WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS)

        if not window_rect_verified:
            raise RuntimeError("WINDOW_PLACEMENT_NOT_VERIFIED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "placement": placement,
            "placement_label_pt": placement_spec.label_pt,
            "position_mode": "monitor_work_area_registered_layout",
            "monitor_work_area_left": work_left,
            "monitor_work_area_top": work_top,
            "monitor_work_area_right": work_right,
            "monitor_work_area_bottom": work_bottom,
            "monitor_work_area_width": work_width,
            "monitor_work_area_height": work_height,
            "target_left": target_left,
            "target_top": target_top,
            "target_right": target_right,
            "target_bottom": target_bottom,
            "target_width": target_width,
            "target_height": target_height,
            "window_rect_verified": True,
            "was_minimized": was_minimized,
            "was_maximized": was_maximized,
            "restored_to_normal_before_move": restored_to_normal,
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_process_name": resolved_process_name,
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_MONITOR_WORK_AREA_REGISTERED_LAYOUT",
            "placement_allowlist": list(ALLOWED_WINDOW_PLACEMENTS),
            "title_match": (
                "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution"
            ),
        }



    def place_window_pair(
        self,
        first_target_token: str,
        second_target_token: str,
        arrangement: str,
    ) -> dict[str, object]:
        if (
            not is_window_target_token(first_target_token)
            or not is_window_target_token(second_target_token)
        ):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if first_target_token == second_target_token:
            raise RuntimeError("WINDOW_PAIR_SAME_TARGET")

        layout_spec = get_window_pair_layout_spec(arrangement)
        if layout_spec is None:
            raise RuntimeError("WINDOW_PAIR_LAYOUT_NOT_ALLOWED")
        first_placement = get_window_placement_spec(layout_spec.first_placement)
        second_placement = get_window_placement_spec(layout_spec.second_placement)
        if first_placement is None or second_placement is None:
            raise RuntimeError("WINDOW_PAIR_LAYOUT_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_MonitorInfo),
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.MoveWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.BOOL,
        ]
        user32.MoveWindow.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL

        (
            all_candidates,
            full_titles,
            dwm_cloaked_by_hwnd,
            _visible_pids,
        ) = self._enumerate_action_window_candidates(
            user32,
            callback_type,
        )

        first_matches = [
            candidate
            for candidate in all_candidates
            if candidate.target_token == first_target_token
        ]
        second_matches = [
            candidate
            for candidate in all_candidates
            if candidate.target_token == second_target_token
        ]

        if not first_matches:
            raise RuntimeError("WINDOW_PAIR_FIRST_TARGET_NOT_FOUND")
        if len(first_matches) != 1:
            raise RuntimeError("WINDOW_PAIR_FIRST_TARGET_AMBIGUOUS")
        if not second_matches:
            raise RuntimeError("WINDOW_PAIR_SECOND_TARGET_NOT_FOUND")
        if len(second_matches) != 1:
            raise RuntimeError("WINDOW_PAIR_SECOND_TARGET_AMBIGUOUS")

        candidate_tuple = all_candidates
        try:
            (
                first_resolved,
                first_visual_frame_normalized,
                first_dwm_tiebreak_used,
            ) = resolve_hosted_visual_frame_with_dwm_tiebreak(
                first_matches[0],
                candidate_tuple,
                dwm_cloaked_by_hwnd,
            )
            (
                second_resolved,
                second_visual_frame_normalized,
                second_dwm_tiebreak_used,
            ) = resolve_hosted_visual_frame_with_dwm_tiebreak(
                second_matches[0],
                candidate_tuple,
                dwm_cloaked_by_hwnd,
            )
        except ValueError as exc:
            if str(exc) == "HOSTED_VISUAL_FRAME_NOT_FOUND":
                raise RuntimeError(
                    "WINDOW_PAIR_VISUAL_FRAME_NOT_FOUND"
                ) from exc
            if str(exc) == "HOSTED_VISUAL_FRAME_AMBIGUOUS":
                raise RuntimeError(
                    "WINDOW_PAIR_VISUAL_FRAME_AMBIGUOUS"
                ) from exc
            raise

        first_hwnd_value = first_resolved.hwnd
        second_hwnd_value = second_resolved.hwnd
        first_pid = first_resolved.pid
        second_pid = second_resolved.pid
        first_full_title = full_titles[first_hwnd_value]
        second_full_title = full_titles[second_hwnd_value]

        if first_hwnd_value == second_hwnd_value:
            raise RuntimeError("WINDOW_PAIR_SAME_TARGET")
        if first_pid == os.getpid() or second_pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_PAIR_PLACEMENT_BLOCKED")

        first_hwnd = wintypes.HWND(first_hwnd_value)
        second_hwnd = wintypes.HWND(second_hwnd_value)

        if (
            first_resolved.is_iconic
            or first_resolved.is_zoomed
            or second_resolved.is_iconic
            or second_resolved.is_zoomed
        ):
            raise RuntimeError("WINDOW_PAIR_NORMAL_STATE_REQUIRED")

        def get_rect(hwnd: wintypes.HWND) -> tuple[int, int, int, int]:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise RuntimeError("WINDOW_PAIR_ORIGINAL_RECT_FAILED")
            return (
                int(rect.left),
                int(rect.top),
                int(rect.right),
                int(rect.bottom),
            )

        first_original = get_rect(first_hwnd)
        second_original = get_rect(second_hwnd)

        first_monitor = user32.MonitorFromWindow(
            first_hwnd,
            MONITOR_DEFAULTTONEAREST,
        )
        second_monitor = user32.MonitorFromWindow(
            second_hwnd,
            MONITOR_DEFAULTTONEAREST,
        )
        if not first_monitor or not second_monitor:
            raise RuntimeError("WINDOW_PAIR_MONITOR_NOT_FOUND")
        if first_monitor != second_monitor:
            raise RuntimeError("WINDOW_PAIR_MONITOR_MISMATCH")

        monitor_info = _MonitorInfo()
        monitor_info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(
            first_monitor,
            ctypes.byref(monitor_info),
        ):
            raise RuntimeError("WINDOW_PAIR_MONITOR_INFO_FAILED")

        work = monitor_info.rcWork
        work_left = int(work.left)
        work_top = int(work.top)
        work_right = int(work.right)
        work_bottom = int(work.bottom)
        work_width = work_right - work_left
        work_height = work_bottom - work_top
        if work_width <= 0 or work_height <= 0:
            raise RuntimeError("WINDOW_PAIR_WORK_AREA_INVALID")

        def target_rect(placement_spec: object) -> tuple[int, int, int, int]:
            x_start = (work_width * placement_spec.x_percent) // 100
            y_start = (work_height * placement_spec.y_percent) // 100
            x_end = (
                work_width
                * (placement_spec.x_percent + placement_spec.width_percent)
            ) // 100
            y_end = (
                work_height
                * (placement_spec.y_percent + placement_spec.height_percent)
            ) // 100
            left = work_left + x_start
            top = work_top + y_start
            right = work_left + x_end
            bottom = work_top + y_end
            if right <= left or bottom <= top:
                raise RuntimeError("WINDOW_PAIR_WORK_AREA_INVALID")
            return left, top, right, bottom

        first_target = target_rect(first_placement)
        second_target = target_rect(second_placement)

        def move_window(
            hwnd: wintypes.HWND,
            rectangle: tuple[int, int, int, int],
        ) -> None:
            left, top, right, bottom = rectangle
            if not user32.MoveWindow(
                hwnd,
                left,
                top,
                right - left,
                bottom - top,
                True,
            ):
                raise RuntimeError("WINDOW_PAIR_MOVE_NOT_ACCEPTED")

        def rect_verified(
            hwnd: wintypes.HWND,
            expected: tuple[int, int, int, int],
        ) -> bool:
            deadline = time.monotonic() + WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS
            while time.monotonic() <= deadline:
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    actual = (
                        int(rect.left),
                        int(rect.top),
                        int(rect.right),
                        int(rect.bottom),
                    )
                    if actual == expected:
                        return True
                time.sleep(WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS)
            return False

        mutation_started = False
        try:
            move_window(first_hwnd, first_target)
            mutation_started = True
            if not rect_verified(first_hwnd, first_target):
                raise RuntimeError("WINDOW_PAIR_NOT_VERIFIED")

            move_window(second_hwnd, second_target)
            if not rect_verified(second_hwnd, second_target):
                raise RuntimeError("WINDOW_PAIR_NOT_VERIFIED")
        except (RuntimeError, OSError) as original_error:
            if mutation_started:
                rollback_ok = True
                for hwnd, rectangle in (
                    (first_hwnd, first_original),
                    (second_hwnd, second_original),
                ):
                    try:
                        move_window(hwnd, rectangle)
                    except (RuntimeError, OSError):
                        rollback_ok = False
                        continue
                    if not rect_verified(hwnd, rectangle):
                        rollback_ok = False
                if not rollback_ok:
                    raise RuntimeError(
                        "WINDOW_PAIR_ROLLBACK_FAILED"
                    ) from original_error
            raise

        try:
            first_process_name = psutil.Process(first_pid).name()
        except psutil.Error:
            first_process_name = "processo-indisponivel"
        try:
            second_process_name = psutil.Process(second_pid).name()
        except psutil.Error:
            second_process_name = "processo-indisponivel"

        return {
            "arrangement": arrangement,
            "arrangement_label_pt": layout_spec.label_pt,
            "first_pid": first_pid,
            "first_title": first_full_title[:MAX_WINDOW_TITLE_CHARS],
            "first_process_name": first_process_name,
            "first_target_token": first_target_token,
            "first_placement": layout_spec.first_placement,
            "first_target_left": first_target[0],
            "first_target_top": first_target[1],
            "first_target_right": first_target[2],
            "first_target_bottom": first_target[3],
            "first_rect_verified": True,
            "second_pid": second_pid,
            "second_title": second_full_title[:MAX_WINDOW_TITLE_CHARS],
            "second_process_name": second_process_name,
            "second_target_token": second_target_token,
            "second_placement": layout_spec.second_placement,
            "second_target_left": second_target[0],
            "second_target_top": second_target[1],
            "second_target_right": second_target[2],
            "second_target_bottom": second_target[3],
            "second_rect_verified": True,
            "same_monitor_verified": True,
            "monitor_work_area_left": work_left,
            "monitor_work_area_top": work_top,
            "monitor_work_area_right": work_right,
            "monitor_work_area_bottom": work_bottom,
            "monitor_work_area_width": work_width,
            "monitor_work_area_height": work_height,
            "windows_moved": 2,
            "transactional_rollback_available": True,
            "rollback_performed": False,
            "normal_state_required": True,
            "token_only_target_resolution": True,
            "hosted_visual_frame_resolution": True,
            "first_visual_frame_normalized": first_visual_frame_normalized,
            "second_visual_frame_normalized": second_visual_frame_normalized,
            "first_visual_frame_dwm_tiebreak_used": first_dwm_tiebreak_used,
            "second_visual_frame_dwm_tiebreak_used": second_dwm_tiebreak_used,
            "dwm_uncloaked_tiebreak_used": (
                first_dwm_tiebreak_used or second_dwm_tiebreak_used
            ),
            "first_resolved_dwm_cloaked": dwm_cloaked_by_hwnd.get(
                first_resolved.hwnd
            ),
            "second_resolved_dwm_cloaked": dwm_cloaked_by_hwnd.get(
                second_resolved.hwnd
            ),
            "first_resolved_window_class": first_resolved.class_name,
            "second_resolved_window_class": second_resolved.class_name,
            "first_requested_target_token": first_target_token,
            "second_requested_target_token": second_target_token,
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_PAIR_REGISTERED_LAYOUT",
            "title_match": "opaque_token_then_hosted_visual_frame_resolution",
        }

    def place_window_set(
        self,
        target_tokens: tuple[str, ...],
        arrangement: str,
    ) -> dict[str, object]:
        if len(target_tokens) not in (3, 4):
            raise RuntimeError("WINDOW_SET_TARGET_COUNT_MISMATCH")
        if any(not is_window_target_token(token) for token in target_tokens):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if len(set(target_tokens)) != len(target_tokens):
            raise RuntimeError("WINDOW_SET_DUPLICATE_TARGET")

        layout_spec = get_window_set_layout_spec(arrangement)
        if layout_spec is None:
            raise RuntimeError("WINDOW_SET_LAYOUT_NOT_ALLOWED")
        if layout_spec.target_count != len(target_tokens):
            raise RuntimeError("WINDOW_SET_TARGET_COUNT_MISMATCH")

        placement_specs = tuple(
            get_window_placement_spec(name)
            for name in layout_spec.placements
        )
        if any(spec is None for spec in placement_specs):
            raise RuntimeError("WINDOW_SET_LAYOUT_NOT_ALLOWED")

        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_MonitorInfo),
        ]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.MoveWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.BOOL,
        ]
        user32.MoveWindow.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL

        (
            all_candidates,
            full_titles,
            dwm_cloaked_by_hwnd,
            _visible_pids,
        ) = self._enumerate_action_window_candidates(
            user32,
            callback_type,
        )

        candidate_tuple = all_candidates
        resolved_candidates: list[HostedWindowCandidate] = []
        normalized_flags: list[bool] = []
        dwm_tiebreak_flags: list[bool] = []

        for index, token in enumerate(target_tokens, start=1):
            matches = [
                candidate
                for candidate in all_candidates
                if candidate.target_token == token
            ]
            if not matches:
                raise RuntimeError(f"WINDOW_SET_TARGET_NOT_FOUND:{index}")
            if len(matches) != 1:
                raise RuntimeError(f"WINDOW_SET_TARGET_AMBIGUOUS:{index}")

            try:
                resolved, normalized, dwm_tiebreak_used = (
                    resolve_hosted_visual_frame_for_set(
                        matches[0],
                        candidate_tuple,
                        dwm_cloaked_by_hwnd,
                    )
                )
            except ValueError as exc:
                if str(exc) == "HOSTED_VISUAL_FRAME_NOT_FOUND":
                    raise RuntimeError(
                        f"WINDOW_SET_VISUAL_FRAME_NOT_FOUND:{index}"
                    ) from exc
                if str(exc) == "HOSTED_VISUAL_FRAME_AMBIGUOUS":
                    raise RuntimeError(
                        f"WINDOW_SET_VISUAL_FRAME_AMBIGUOUS:{index}"
                    ) from exc
                raise

            resolved_candidates.append(resolved)
            normalized_flags.append(normalized)
            dwm_tiebreak_flags.append(dwm_tiebreak_used)

        if len({candidate.hwnd for candidate in resolved_candidates}) != len(
            resolved_candidates
        ):
            raise RuntimeError("WINDOW_SET_SAME_RESOLVED_TARGET")

        if any(candidate.pid == os.getpid() for candidate in resolved_candidates):
            raise RuntimeError("SELF_WINDOW_SET_PLACEMENT_BLOCKED")

        if any(
            candidate.is_iconic or candidate.is_zoomed
            for candidate in resolved_candidates
        ):
            raise RuntimeError("WINDOW_SET_NORMAL_STATE_REQUIRED")

        hwnds = tuple(
            wintypes.HWND(candidate.hwnd)
            for candidate in resolved_candidates
        )

        def get_rect(hwnd: wintypes.HWND) -> tuple[int, int, int, int]:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise RuntimeError("WINDOW_SET_ORIGINAL_RECT_FAILED")
            return (
                int(rect.left),
                int(rect.top),
                int(rect.right),
                int(rect.bottom),
            )

        originals = tuple(get_rect(hwnd) for hwnd in hwnds)

        monitors = tuple(
            user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            for hwnd in hwnds
        )
        if any(not monitor for monitor in monitors):
            raise RuntimeError("WINDOW_SET_MONITOR_NOT_FOUND")
        first_monitor = monitors[0]
        if any(monitor != first_monitor for monitor in monitors[1:]):
            raise RuntimeError("WINDOW_SET_MONITOR_MISMATCH")

        monitor_info = _MonitorInfo()
        monitor_info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(
            first_monitor,
            ctypes.byref(monitor_info),
        ):
            raise RuntimeError("WINDOW_SET_MONITOR_INFO_FAILED")

        work = monitor_info.rcWork
        work_left = int(work.left)
        work_top = int(work.top)
        work_right = int(work.right)
        work_bottom = int(work.bottom)
        work_width = work_right - work_left
        work_height = work_bottom - work_top
        if work_width <= 0 or work_height <= 0:
            raise RuntimeError("WINDOW_SET_WORK_AREA_INVALID")

        def target_rect(placement_spec: object) -> tuple[int, int, int, int]:
            x_start = (work_width * placement_spec.x_percent) // 100
            y_start = (work_height * placement_spec.y_percent) // 100
            x_end = (
                work_width
                * (placement_spec.x_percent + placement_spec.width_percent)
            ) // 100
            y_end = (
                work_height
                * (placement_spec.y_percent + placement_spec.height_percent)
            ) // 100
            left = work_left + x_start
            top = work_top + y_start
            right = work_left + x_end
            bottom = work_top + y_end
            if right <= left or bottom <= top:
                raise RuntimeError("WINDOW_SET_WORK_AREA_INVALID")
            return left, top, right, bottom

        targets = tuple(
            target_rect(placement_spec)
            for placement_spec in placement_specs
        )

        def move_window(
            hwnd: wintypes.HWND,
            rectangle: tuple[int, int, int, int],
        ) -> None:
            left, top, right, bottom = rectangle
            if not user32.MoveWindow(
                hwnd,
                left,
                top,
                right - left,
                bottom - top,
                True,
            ):
                raise RuntimeError("WINDOW_SET_MOVE_NOT_ACCEPTED")

        def rect_verified(
            hwnd: wintypes.HWND,
            expected: tuple[int, int, int, int],
        ) -> bool:
            deadline = time.monotonic() + WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS
            while time.monotonic() <= deadline:
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    actual = (
                        int(rect.left),
                        int(rect.top),
                        int(rect.right),
                        int(rect.bottom),
                    )
                    if actual == expected:
                        return True
                time.sleep(WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS)
            return False

        mutation_started = False
        try:
            for index, (hwnd, target) in enumerate(
                zip(hwnds, targets, strict=True),
                start=1,
            ):
                move_window(hwnd, target)
                mutation_started = True
                if not rect_verified(hwnd, target):
                    raise RuntimeError(f"WINDOW_SET_NOT_VERIFIED:{index}")
        except (RuntimeError, OSError) as original_error:
            if mutation_started:
                rollback_ok = True
                for hwnd, original in zip(hwnds, originals, strict=True):
                    try:
                        move_window(hwnd, original)
                    except (RuntimeError, OSError):
                        rollback_ok = False
                        continue
                    if not rect_verified(hwnd, original):
                        rollback_ok = False
                if not rollback_ok:
                    raise RuntimeError(
                        "WINDOW_SET_ROLLBACK_FAILED"
                    ) from original_error
            raise

        target_evidence: list[dict[str, object]] = []
        for index, (
            requested_token,
            candidate,
            normalized,
            dwm_tiebreak_used,
            placement_name,
            target,
        ) in enumerate(
            zip(
                target_tokens,
                resolved_candidates,
                normalized_flags,
                dwm_tiebreak_flags,
                layout_spec.placements,
                targets,
                strict=True,
            ),
            start=1,
        ):
            try:
                process_name = psutil.Process(candidate.pid).name()
            except psutil.Error:
                process_name = "processo-indisponivel"

            target_evidence.append(
                {
                    "index": index,
                    "pid": candidate.pid,
                    "title": full_titles[candidate.hwnd][
                        :MAX_WINDOW_TITLE_CHARS
                    ],
                    "process_name": process_name,
                    "requested_target_token": requested_token,
                    "placement": placement_name,
                    "target_left": target[0],
                    "target_top": target[1],
                    "target_right": target[2],
                    "target_bottom": target[3],
                    "rect_verified": True,
                    "resolved_window_class": candidate.class_name,
                    "visual_frame_normalized": normalized,
                    "visual_frame_dwm_tiebreak_used": dwm_tiebreak_used,
                    "resolved_dwm_cloaked": dwm_cloaked_by_hwnd.get(
                        candidate.hwnd
                    ),
                }
            )

        return {
            "arrangement": arrangement,
            "arrangement_label_pt": layout_spec.label_pt,
            "window_count": len(target_evidence),
            "targets": target_evidence,
            "same_monitor_verified": True,
            "monitor_work_area_left": work_left,
            "monitor_work_area_top": work_top,
            "monitor_work_area_right": work_right,
            "monitor_work_area_bottom": work_bottom,
            "monitor_work_area_width": work_width,
            "monitor_work_area_height": work_height,
            "windows_moved": len(target_evidence),
            "transactional_rollback_available": True,
            "rollback_performed": False,
            "normal_state_required": True,
            "token_only_target_resolution": True,
            "hosted_visual_frame_resolution": True,
            "dwm_uncloaked_tiebreak_used": any(dwm_tiebreak_flags),
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_SET_REGISTERED_LAYOUT",
            "title_match": "opaque_token_then_hosted_visual_frame_resolution",
        }


    def restore_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_RESTORE_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        if resolved_candidate.pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_RESTORE_BLOCKED")
        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        was_minimized = bool(user32.IsIconic(hwnd))
        was_maximized = bool(user32.IsZoomed(hwnd))

        if was_minimized or was_maximized:
            user32.ShowWindow(hwnd, SW_RESTORE)

        deadline = time.monotonic() + WINDOW_RESTORE_VERIFY_TIMEOUT_SECONDS
        restored_verified = False
        while time.monotonic() <= deadline:
            is_minimized = bool(user32.IsIconic(hwnd))
            is_maximized = bool(user32.IsZoomed(hwnd))
            if not is_minimized and not is_maximized:
                restored_verified = True
                break
            time.sleep(WINDOW_RESTORE_VERIFY_INTERVAL_SECONDS)

        if not restored_verified:
            raise RuntimeError("WINDOW_RESTORE_NOT_VERIFIED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "restored": True,
            "restored_verified": True,
            "was_minimized": was_minimized,
            "was_maximized": was_maximized,
            "state": "normal",
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_process_name": resolved_process_name,
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def maximize_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MAXIMIZE_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        if resolved_candidate.pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MAXIMIZE_BLOCKED")
        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        was_maximized = bool(user32.IsZoomed(hwnd))

        if not was_maximized:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)

        deadline = time.monotonic() + WINDOW_MAXIMIZE_VERIFY_TIMEOUT_SECONDS
        maximized_verified = False
        while time.monotonic() <= deadline:
            if user32.IsZoomed(hwnd):
                maximized_verified = True
                break
            time.sleep(WINDOW_MAXIMIZE_VERIFY_INTERVAL_SECONDS)

        if not maximized_verified:
            raise RuntimeError("WINDOW_MAXIMIZE_NOT_VERIFIED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "maximized": True,
            "maximized_verified": True,
            "already_maximized": was_maximized,
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_process_name": resolved_process_name,
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def minimize_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MINIMIZE_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
        )
        if resolved_candidate.pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MINIMIZE_BLOCKED")
        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        was_minimized = bool(user32.IsIconic(hwnd))

        if not was_minimized:
            user32.ShowWindow(hwnd, SW_MINIMIZE)

        deadline = time.monotonic() + WINDOW_MINIMIZE_VERIFY_TIMEOUT_SECONDS
        minimized_verified = False
        while time.monotonic() <= deadline:
            if user32.IsIconic(hwnd):
                minimized_verified = True
                break
            time.sleep(WINDOW_MINIMIZE_VERIFY_INTERVAL_SECONDS)

        if not minimized_verified:
            raise RuntimeError("WINDOW_MINIMIZE_NOT_VERIFIED")

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "minimized": True,
            "minimized_verified": True,
            "already_minimized": was_minimized,
            "hosted_visual_frame_resolution": True,
            "visual_frame_normalized": visual_frame_normalized,
            "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
            "resolved_pid": resolved_pid,
            "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "resolved_process_name": resolved_process_name,
            "resolved_window_class": resolved_candidate.class_name,
            "resolved_dwm_cloaked": resolved_dwm_cloaked,
            "requested_pid": pid,
            "requested_title": title,
            "requested_target_token": target_token,
            "requested_window_class": requested_candidate.class_name,
            "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
            "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
        }

    def close_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_CLOSE_BLOCKED")
        if not is_window_target_token(target_token):
            raise RuntimeError("WINDOW_TARGET_TOKEN_INVALID")
        if not hasattr(ctypes, "WinDLL") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise RuntimeError("WINDOWS_API_UNAVAILABLE")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        (
            requested_candidate,
            resolved_candidate,
            requested_full_title,
            full_title,
            visual_frame_normalized,
            visual_frame_dwm_tiebreak_used,
            resolved_dwm_cloaked,
        ) = self._resolve_exact_window_target(
            user32,
            callback_type,
            pid,
            title,
            target_token,
            stale_detail=True,
        )
        if resolved_candidate.pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_CLOSE_BLOCKED")
        hwnd_value = resolved_candidate.hwnd
        resolved_pid = resolved_candidate.pid
        hwnd = wintypes.HWND(hwnd_value)

        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"
        try:
            resolved_process_name = psutil.Process(resolved_pid).name()
        except psutil.Error:
            resolved_process_name = "processo-indisponivel"

        if not user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_CLOSE, 0):
            error_code = ctypes.get_last_error()
            raise OSError(
                error_code,
                "PostMessageW(WM_SYSCOMMAND, SC_CLOSE) failed",
            )

        deadline = time.monotonic() + WINDOW_CLOSE_VERIFY_TIMEOUT_SECONDS
        while time.monotonic() <= deadline:
            window_exists = bool(user32.IsWindow(hwnd))
            window_visible = bool(user32.IsWindowVisible(hwnd)) if window_exists else False
            if not window_exists or not window_visible:
                return {
                    "pid": pid,
                    "title": full_title[:MAX_WINDOW_TITLE_CHARS],
                    "process_name": process_name,
                    "target_token": target_token,
                    "close_requested": True,
                    "window_gone_verified": True,
                    "verification": "original_exact_window_destroyed_or_not_visible",
                    "close_method": "WM_SYSCOMMAND_SC_CLOSE",
                    "force_kill_used": False,
                    "hosted_visual_frame_resolution": True,
                    "visual_frame_normalized": visual_frame_normalized,
                    "visual_frame_dwm_tiebreak_used": visual_frame_dwm_tiebreak_used,
                    "resolved_pid": resolved_pid,
                    "resolved_title": full_title[:MAX_WINDOW_TITLE_CHARS],
                    "resolved_process_name": resolved_process_name,
                    "resolved_window_class": resolved_candidate.class_name,
                    "resolved_dwm_cloaked": resolved_dwm_cloaked,
                    "requested_pid": pid,
                    "requested_title": title,
                    "requested_target_token": target_token,
                    "requested_window_class": requested_candidate.class_name,
                    "requested_full_title": requested_full_title[:MAX_WINDOW_TITLE_CHARS],
                    "title_match": "pid_bounded_title_and_opaque_token_then_hosted_visual_frame_resolution",
                }
            time.sleep(WINDOW_CLOSE_VERIFY_INTERVAL_SECONDS)

        raise RuntimeError("WINDOW_CLOSE_NOT_VERIFIED")
