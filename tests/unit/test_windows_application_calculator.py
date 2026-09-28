from __future__ import annotations

from theos.core.applications.registry import ResolvedApplication
from theos.integrations.windows.applications import WindowsApplicationAdapter


class _FakeProcess:
    def __init__(self, pid: int, name: str, exe: str) -> None:
        self.info = {
            "pid": pid,
            "name": name,
            "exe": exe,
        }


def test_calculator_verification_accepts_runtime_process_name(monkeypatch) -> None:
    app = ResolvedApplication(
        name="Calculator",
        target=r"C:\Windows\System32\calc.exe",
        process_names=(
            "calc.exe",
            "CalculatorApp.exe",
            "Calculator.exe",
        ),
    )

    monkeypatch.setattr(
        "theos.integrations.windows.applications.psutil.process_iter",
        lambda _attrs: [
            _FakeProcess(
                2468,
                "CalculatorApp.exe",
                r"C:\Program Files\WindowsApps\CalculatorApp.exe",
            )
        ],
    )

    evidence = WindowsApplicationAdapter().verify_running(
        app,
        timeout_seconds=0.01,
    )

    assert evidence["verified"] is True
    assert evidence["processes"] == [
        {
            "pid": 2468,
            "name": "CalculatorApp.exe",
            "exe": r"C:\Program Files\WindowsApps\CalculatorApp.exe",
        }
    ]
