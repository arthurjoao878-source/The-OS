from __future__ import annotations

import psutil

MAX_PROCESS_RESULTS = 12


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
