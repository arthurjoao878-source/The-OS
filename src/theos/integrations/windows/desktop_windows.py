from __future__ import annotations

import ctypes
from ctypes import wintypes

import psutil

MAX_WINDOW_RESULTS = 12
MAX_WINDOW_TITLE_CHARS = 160


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
