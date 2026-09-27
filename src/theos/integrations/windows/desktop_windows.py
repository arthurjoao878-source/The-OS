from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

import psutil

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
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060


class WindowsDesktopWindowAdapter:
    def snapshot(self) -> dict[str, object]:
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

            rows.append(
                {
                    "title": title[:MAX_WINDOW_TITLE_CHARS],
                    "pid": pid,
                    "process_name": process_name,
                }
            )
            return True

        callback = callback_type(visit_window)
        if not user32.EnumWindows(callback, 0):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "EnumWindows failed")

        selected = rows[:MAX_WINDOW_RESULTS]
        return {
            "observed_windows": len(rows),
            "returned_windows": len(selected),
            "max_results": MAX_WINDOW_RESULTS,
            "max_title_chars": MAX_WINDOW_TITLE_CHARS,
            "order": "windows_z_order",
            "fields": ["title", "pid", "process_name"],
            "windows": selected,
        }

    def activate_window(self, pid: int, title: str) -> dict[str, object]:
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
            if bounded_title == title:
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
            "activated": True,
            "foreground_verified": True,
            "restored_from_minimized": was_minimized,
            "title_match": "bounded_title_exact",
        }

    def maximize_window(self, pid: int, title: str) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MAXIMIZE_BLOCKED")
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
            if bounded_title == title:
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
            "maximized": True,
            "maximized_verified": True,
            "already_maximized": was_maximized,
            "title_match": "bounded_title_exact",
        }

    def minimize_window(self, pid: int, title: str) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_MINIMIZE_BLOCKED")
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
            if bounded_title == title:
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
            "minimized": True,
            "minimized_verified": True,
            "already_minimized": was_minimized,
            "title_match": "bounded_title_exact",
        }

    def close_window(self, pid: int, title: str) -> dict[str, object]:
        if pid == os.getpid():
            raise RuntimeError("SELF_WINDOW_CLOSE_BLOCKED")
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
            if bounded_title == title:
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
                    "close_requested": True,
                    "window_gone_verified": True,
                    "verification": "original_window_destroyed_or_not_visible",
                    "close_method": "WM_SYSCOMMAND_SC_CLOSE",
                    "force_kill_used": False,
                }
            time.sleep(WINDOW_CLOSE_VERIFY_INTERVAL_SECONDS)

        raise RuntimeError("WINDOW_CLOSE_NOT_VERIFIED")
