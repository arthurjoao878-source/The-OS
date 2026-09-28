from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

_LEADING_PORTUGUESE_ARTICLES = frozenset({"a", "o", "um", "uma"})


def normalize_application_name(raw_name: str) -> str:
    normalized = " ".join(raw_name.strip().split())
    if not normalized:
        return ""

    first, separator, remainder = normalized.partition(" ")
    if (
        separator
        and first.casefold() in _LEADING_PORTUGUESE_ARTICLES
        and remainder.strip()
    ):
        return remainder.strip()

    return normalized


@dataclass(frozen=True)
class ResolvedApplication:
    name: str
    target: str
    process_names: tuple[str, ...]


class ApplicationRegistry:
    _ALIASES: ClassVar[dict[str, tuple[str, str]]] = {
        "discord": ("Discord", "Discord.exe"),
        "chrome": ("Google Chrome", "chrome.exe"),
        "google chrome": ("Google Chrome", "chrome.exe"),
        "vscode": ("Visual Studio Code", "Code.exe"),
        "vs code": ("Visual Studio Code", "Code.exe"),
        "code": ("Visual Studio Code", "Code.exe"),
        "notepad": ("Notepad", "notepad.exe"),
        "bloco de notas": ("Notepad", "notepad.exe"),
        "calculator": ("Calculator", "calc.exe"),
        "calculadora": ("Calculator", "calc.exe"),
        "calc": ("Calculator", "calc.exe"),
    }

    def resolve(self, raw_name: str) -> ResolvedApplication | None:
        normalized_name = normalize_application_name(raw_name)
        if not normalized_name:
            return None

        key = normalized_name.casefold()
        item = self._ALIASES.get(key)
        if item is None:
            item = (normalized_name, normalized_name)

        display_name, exe_name = item

        from_path = shutil.which(exe_name)
        if from_path:
            process_names = (Path(from_path).name,)
            if exe_name.casefold() == "calc.exe":
                process_names = (
                    "calc.exe",
                    "CalculatorApp.exe",
                    "Calculator.exe",
                )
            return ResolvedApplication(display_name, from_path, process_names)

        if exe_name.lower() == "discord.exe":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                update = Path(local) / "Discord" / "Update.exe"
                if update.exists():
                    return ResolvedApplication(
                        "Discord",
                        str(update),
                        ("Discord.exe",),
                    )

        if exe_name.lower() == "chrome.exe":
            candidates = [
                Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
                Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return ResolvedApplication("Google Chrome", str(candidate), ("chrome.exe",))

        if exe_name.lower() == "code.exe":
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
                Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft VS Code/Code.exe",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return ResolvedApplication("Visual Studio Code", str(candidate), ("Code.exe",))

        return None