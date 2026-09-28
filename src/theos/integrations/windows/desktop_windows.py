from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import secrets
import time
from ctypes import wintypes

import psutil

from theos.core.window_keys import ALLOWED_WINDOW_KEYS
from theos.core.window_targets import (
    is_window_target_token,
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
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
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
}
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
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

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
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
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
        hwnd = wintypes.HWND(hwnd_value)
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

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "activated": True,
            "foreground_verified": True,
            "restored_from_minimized": was_minimized,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
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
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
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
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
        hwnd = wintypes.HWND(hwnd_value)
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
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
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
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
        hwnd = wintypes.HWND(hwnd_value)
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

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "maximized": True,
            "maximized_verified": True,
            "already_maximized": was_maximized,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
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
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL

        matches: list[tuple[int, str]] = []

        def visit_window(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
        hwnd = wintypes.HWND(hwnd_value)
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

        return {
            "pid": pid,
            "title": full_title[:MAX_WINDOW_TITLE_CHARS],
            "process_name": process_name,
            "target_token": target_token,
            "minimized": True,
            "minimized_verified": True,
            "already_minimized": was_minimized,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
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

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
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
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL

        matches: list[tuple[int, str]] = []
        visible_pid_matches = 0
        visible_pid_title_matches = 0

        def visit_window(hwnd: int, _lparam: int) -> bool:
            nonlocal visible_pid_matches, visible_pid_title_matches

            if not user32.IsWindowVisible(hwnd):
                return True

            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )
            if int(process_id.value) != pid:
                return True

            visible_pid_matches += 1

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

            full_title = buffer.value.strip()
            if not full_title:
                return True

            bounded_title = full_title[:MAX_WINDOW_TITLE_CHARS]
            if bounded_title != title:
                return True

            visible_pid_title_matches += 1

            candidate_token = _window_target_token(
                int(hwnd),
                pid,
                bounded_title,
            )
            if candidate_token == target_token:
                matches.append((int(hwnd), full_title))
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        if not matches:
            if visible_pid_title_matches:
                raise RuntimeError("WINDOW_TARGET_TOKEN_STALE")
            if visible_pid_matches:
                raise RuntimeError("WINDOW_TARGET_TITLE_CHANGED")
            raise RuntimeError("WINDOW_TARGET_NOT_FOUND")
        if len(matches) != 1:
            raise RuntimeError("WINDOW_TARGET_AMBIGUOUS")

        hwnd_value, full_title = matches[0]
        hwnd = wintypes.HWND(hwnd_value)

        try:
            process_name = psutil.Process(pid).name()
        except psutil.Error:
            process_name = "processo-indisponivel"

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
                    "title_match": "pid_bounded_title_and_opaque_token_exact",
                }
            time.sleep(WINDOW_CLOSE_VERIFY_INTERVAL_SECONDS)

        raise RuntimeError("WINDOW_CLOSE_NOT_VERIFIED")
