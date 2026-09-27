from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


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
    }

    def resolve(self, raw_name: str) -> ResolvedApplication | None:
        key = raw_name.strip().lower()
        item = self._ALIASES.get(key)
        if item is None:
            item = (raw_name.strip(), raw_name.strip())

        display_name, exe_name = item

        from_path = shutil.which(exe_name)
        if from_path:
            return ResolvedApplication(display_name, from_path, (Path(exe_name).name,))

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