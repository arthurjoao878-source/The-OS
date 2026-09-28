from __future__ import annotations

from theos.core.applications.registry import (
    ApplicationRegistry,
    normalize_application_name,
)


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


def test_normalize_application_name_removes_one_common_portuguese_article() -> None:
    assert normalize_application_name("  um   bloco de notas  ") == "bloco de notas"
    assert normalize_application_name("UMA   PowerShell") == "PowerShell"
    assert normalize_application_name("o Google Chrome") == "Google Chrome"
    assert normalize_application_name("a calculadora") == "calculadora"
    assert normalize_application_name("um") == "um"


def test_registry_resolves_natural_notepad_phrase(monkeypatch) -> None:
    requested: list[str] = []

    def fake_which(name: str) -> str | None:
        requested.append(name)
        if name == "notepad.exe":
            return r"C:\Windows\System32\notepad.exe"
        return None

    monkeypatch.setattr(
        "theos.core.applications.registry.shutil.which",
        fake_which,
    )

    app = ApplicationRegistry().resolve("  um   bloco de notas  ")

    assert app is not None
    assert app.name == "Notepad"
    assert app.target == r"C:\Windows\System32\notepad.exe"
    assert app.process_names == ("notepad.exe",)
    assert requested == ["notepad.exe"]


def test_registry_resolves_calculator_alias_with_runtime_variants(monkeypatch) -> None:
    requested: list[str] = []

    def fake_which(name: str) -> str | None:
        requested.append(name)
        if name == "calc.exe":
            return r"C:\Windows\System32\calc.exe"
        return None

    monkeypatch.setattr(
        "theos.core.applications.registry.shutil.which",
        fake_which,
    )

    app = ApplicationRegistry().resolve("a calculadora")

    assert app is not None
    assert app.name == "Calculator"
    assert app.target == r"C:\Windows\System32\calc.exe"
    assert app.process_names == (
        "calc.exe",
        "CalculatorApp.exe",
        "Calculator.exe",
    )
    assert requested == ["calc.exe"]
