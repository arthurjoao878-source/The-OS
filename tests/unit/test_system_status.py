from __future__ import annotations

from types import SimpleNamespace

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.system_status import SystemStatusAction
from theos.integrations.windows import system_status as system_status_module
from theos.integrations.windows.system_status import WindowsSystemStatusAdapter


def test_windows_system_status_snapshot_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("SystemDrive", "Z:")
    monkeypatch.setattr(
        system_status_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            total=16_000,
            available=10_000,
            percent=37.5,
        ),
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "disk_usage",
        lambda root: SimpleNamespace(
            total=100_000,
            free=40_000,
            percent=60.0,
        )
        if root == "Z:\\"
        else None,
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "cpu_percent",
        lambda *, interval: 12.34 if interval == 0.1 else -1,
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "cpu_count",
        lambda *, logical: 16 if logical else 8,
    )
    monkeypatch.setattr(
        system_status_module.psutil,
        "sensors_battery",
        lambda: SimpleNamespace(percent=78.9, power_plugged=True),
    )

    snapshot = WindowsSystemStatusAdapter().snapshot()

    assert snapshot == {
        "cpu_percent": 12.3,
        "logical_cpu_count": 16,
        "physical_cpu_count": 8,
        "memory_total_bytes": 16_000,
        "memory_available_bytes": 10_000,
        "memory_percent": 37.5,
        "disk_root": "Z:\\",
        "disk_total_bytes": 100_000,
        "disk_free_bytes": 40_000,
        "disk_percent": 60.0,
        "battery_available": True,
        "battery_percent": 78.9,
        "battery_plugged": True,
    }


class _FakeSystemStatusAdapter:
    @staticmethod
    def snapshot() -> dict[str, object]:
        return {
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 30.0,
        }


def test_system_status_action_is_read_only() -> None:
    action = SystemStatusAction(_FakeSystemStatusAdapter())
    request = ActionRequest(action="system_status", arguments={})

    result = action.execute(request)

    assert action.risk is ActionRisk.READ_ONLY
    assert result.success is True
    assert result.message == (
        "Status do sistema coletado: CPU 10.0%, memória 20.0%, disco 30.0%."
    )
    assert result.evidence["cpu_percent"] == 10.0
