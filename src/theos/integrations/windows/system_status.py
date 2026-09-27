from __future__ import annotations

import os

import psutil


class WindowsSystemStatusAdapter:
    # Collects a bounded, read-only Windows system resource snapshot.

    def snapshot(self) -> dict[str, object]:
        memory = psutil.virtual_memory()

        system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/")
        disk_root = f"{system_drive}\\"
        disk = psutil.disk_usage(disk_root)

        battery = psutil.sensors_battery()

        evidence: dict[str, object] = {
            "cpu_percent": round(float(psutil.cpu_percent(interval=0.1)), 1),
            "logical_cpu_count": psutil.cpu_count(logical=True),
            "physical_cpu_count": psutil.cpu_count(logical=False),
            "memory_total_bytes": int(memory.total),
            "memory_available_bytes": int(memory.available),
            "memory_percent": round(float(memory.percent), 1),
            "disk_root": disk_root,
            "disk_total_bytes": int(disk.total),
            "disk_free_bytes": int(disk.free),
            "disk_percent": round(float(disk.percent), 1),
            "battery_available": battery is not None,
        }

        if battery is not None:
            evidence["battery_percent"] = round(float(battery.percent), 1)
            evidence["battery_plugged"] = bool(battery.power_plugged)

        return evidence
