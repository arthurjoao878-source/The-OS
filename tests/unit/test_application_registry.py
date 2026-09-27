from __future__ import annotations

from theos.core.applications.registry import ApplicationRegistry


def test_path_resolution_uses_actual_executable_filename(monkeypatch) -> None:
    resolved = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

    monkeypatch.setattr(
        "theos.core.applications.registry.shutil.which",
        lambda _name: resolved,
    )

    app = ApplicationRegistry().resolve("PowerShell")

    assert app is not None
    assert app.target == resolved
    assert app.process_names == ("powershell.exe",)