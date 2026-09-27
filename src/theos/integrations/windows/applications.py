from __future__ import annotations

import subprocess
import time
from pathlib import Path

import psutil

from theos.core.applications.registry import ResolvedApplication


class WindowsApplicationAdapter:
    def launch(self, app: ResolvedApplication) -> int:
        target = Path(app.target)
        if target.name.lower() == "update.exe" and app.name == "Discord":
            process = subprocess.Popen(
                [str(target), "--processStart", "Discord.exe"],
                close_fds=True,
            )
        else:
            process = subprocess.Popen([str(target)], close_fds=True)
        return process.pid

    def verify_running(
        self,
        app: ResolvedApplication,
        timeout_seconds: float = 8.0,
    ) -> dict[str, object]:
        expected = {name.lower() for name in app.process_names}
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            found: list[dict[str, object]] = []
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if name in expected:
                        found.append(
                            {
                                "pid": proc.info["pid"],
                                "name": proc.info.get("name"),
                                "exe": proc.info.get("exe"),
                            }
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if found:
                return {"verified": True, "processes": found}
            time.sleep(0.2)

        return {"verified": False, "processes": []}