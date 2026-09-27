from __future__ import annotations

import os

import psutil

MAX_PROCESS_RESULTS = 12
PROCESS_TERMINATION_TIMEOUT_SECONDS = 3.0

_PROTECTED_PROCESS_NAMES = frozenset(
    {
        "csrss.exe",
        "fontdrvhost.exe",
        "idle",
        "lsass.exe",
        "memory compression",
        "registry",
        "secure system",
        "services.exe",
        "smss.exe",
        "svchost.exe",
        "system",
        "system idle process",
        "wininit.exe",
        "winlogon.exe",
    }
)


class WindowsProcessAdapter:
    def snapshot(self) -> dict[str, object]:
        rows: list[dict[str, object]] = []

        for process in psutil.process_iter(
            attrs=["pid", "name", "memory_info"],
            ad_value=None,
        ):
            info = process.info
            pid = info.get("pid")
            memory_info = info.get("memory_info")
            if not isinstance(pid, int) or memory_info is None:
                continue

            name = str(info.get("name") or "processo-sem-nome")
            rows.append(
                {
                    "pid": pid,
                    "name": name,
                    "rss_bytes": int(memory_info.rss),
                }
            )

        rows.sort(
            key=lambda row: (
                -int(row["rss_bytes"]),
                str(row["name"]).casefold(),
                int(row["pid"]),
            )
        )
        selected = rows[:MAX_PROCESS_RESULTS]

        return {
            "observed_processes": len(rows),
            "returned_processes": len(selected),
            "max_results": MAX_PROCESS_RESULTS,
            "sort": "rss_bytes_desc",
            "fields": ["pid", "name", "rss_bytes"],
            "processes": selected,
        }

    @staticmethod
    def _is_protected_process(pid: int, name: str) -> bool:
        return (
            pid in {0, 4, os.getpid()}
            or name.casefold() in _PROTECTED_PROCESS_NAMES
        )

    def preview_terminate_process(self, pid: int) -> dict[str, object]:
        evidence: dict[str, object] = {
            "pid": pid,
            "allowed": False,
        }
        if pid <= 0:
            evidence["error"] = "INVALID_PID"
            return evidence
        if pid == os.getpid():
            evidence["error"] = "SELF_TERMINATION_BLOCKED"
            return evidence

        try:
            process = psutil.Process(pid)
            name = process.name()
            create_time = float(process.create_time())
        except psutil.NoSuchProcess:
            evidence["error"] = "PROCESS_NOT_FOUND"
            return evidence
        except psutil.AccessDenied:
            evidence["error"] = "PROCESS_ACCESS_DENIED"
            return evidence

        if self._is_protected_process(pid, name):
            evidence.update(
                {
                    "name": name,
                    "create_time": create_time,
                    "error": "PROTECTED_PROCESS",
                }
            )
            return evidence

        evidence.update(
            {
                "allowed": True,
                "name": name,
                "create_time": create_time,
            }
        )
        return evidence

    def terminate_process(
        self,
        pid: int,
        *,
        expected_name: str,
        expected_create_time: float,
    ) -> dict[str, object]:
        preview = self.preview_terminate_process(pid)
        if not bool(preview.get("allowed")):
            raise RuntimeError(str(preview.get("error", "PROCESS_TERMINATION_BLOCKED")))

        actual_name = str(preview["name"])
        actual_create_time = float(preview["create_time"])
        if (
            actual_name != expected_name
            or abs(actual_create_time - expected_create_time) > 0.000001
        ):
            raise RuntimeError("PROCESS_IDENTITY_CHANGED")

        try:
            process = psutil.Process(pid)
            if (
                process.name() != expected_name
                or abs(float(process.create_time()) - expected_create_time) > 0.000001
            ):
                raise RuntimeError("PROCESS_IDENTITY_CHANGED")

            process.terminate()
            exit_code = process.wait(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
        except psutil.NoSuchProcess:
            exit_code = None
        except psutil.TimeoutExpired as exc:
            raise RuntimeError("PROCESS_TERMINATION_TIMEOUT") from exc

        if process.is_running():
            raise RuntimeError("PROCESS_STILL_RUNNING")

        return {
            "pid": pid,
            "name": expected_name,
            "create_time": expected_create_time,
            "terminated": True,
            "verified_exited": True,
            "exit_code": exit_code,
            "termination_method": "psutil_terminate",
            "kill_fallback_used": False,
        }
