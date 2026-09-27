from __future__ import annotations

from types import SimpleNamespace

from theos.core.applications.registry import ResolvedApplication
from theos.integrations.windows.applications import WindowsApplicationAdapter


def test_powershell_launch_uses_new_console(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(
        "theos.integrations.windows.applications.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "theos.integrations.windows.applications.subprocess.CREATE_NEW_CONSOLE",
        16,
        raising=False,
    )

    app = ResolvedApplication(
        name="PowerShell",
        target=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        process_names=("powershell.exe",),
    )

    pid = WindowsApplicationAdapter().launch(app)

    assert pid == 4242
    assert captured["args"] == [app.target]
    assert captured["kwargs"]["close_fds"] is True
    assert captured["kwargs"]["creationflags"] == 16


def test_gui_application_does_not_force_new_console(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(pid=5151)

    monkeypatch.setattr(
        "theos.integrations.windows.applications.subprocess.Popen",
        fake_popen,
    )

    app = ResolvedApplication(
        name="Notepad",
        target=r"C:\Windows\System32\notepad.exe",
        process_names=("notepad.exe",),
    )

    pid = WindowsApplicationAdapter().launch(app)

    assert pid == 5151
    assert captured["args"] == [app.target]
    assert captured["kwargs"] == {"close_fds": True}