from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import (
    FindPathAction,
    InspectPathAction,
    OpenPathAction,
    ReadTextFileAction,
)
from theos.integrations.windows.file_system import (
    MAX_READ_BYTES,
    WindowsFileSystemAdapter,
)


def test_inspect_file_returns_bounded_metadata(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    action = InspectPathAction(WindowsFileSystemAdapter())
    result = action.execute(
        ActionRequest(
            action="inspect_path",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["kind"] == "file"
    assert result.evidence["size_bytes"] == 5
    assert result.evidence["suffix"] == ".txt"


def test_inspect_directory_lists_entries(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")

    result = InspectPathAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="inspect_path",
            arguments={"path": str(tmp_path)},
        )
    )

    assert result.success is True
    names = [entry["name"] for entry in result.evidence["entries"]]
    assert names == ["folder", "readme.md"]


def test_find_path_matches_names_with_bounded_search(tmp_path: Path) -> None:
    nested = tmp_path / "docs"
    nested.mkdir()
    wanted = nested / "Project-README.md"
    wanted.write_text("x", encoding="utf-8")

    result = FindPathAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="find_path",
            arguments={
                "root": str(tmp_path),
                "query": "readme",
            },
        )
    )

    assert result.success is True
    assert result.evidence["matches"] == [
        {
            "path": str(wanted.resolve()),
            "name": "Project-README.md",
            "kind": "file",
        }
    ]


def test_open_path_requires_confirmation_for_executable_suffixes() -> None:
    risky = ActionRequest(
        action="open_path",
        arguments={"path": r"C:\Temp\script.ps1"},
    )
    normal = ActionRequest(
        action="open_path",
        arguments={"path": r"C:\Temp\notes.txt"},
    )

    assert OpenPathAction.risk_for(risky) is ActionRisk.CONFIRM
    assert OpenPathAction.risk_for(normal) is ActionRisk.NORMAL


def test_open_path_submits_existing_path_to_windows(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    opened: list[str] = []

    monkeypatch.setattr(
        "theos.integrations.windows.file_system.os.startfile",
        lambda path: opened.append(path),
        raising=False,
    )

    result = OpenPathAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="open_path",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["shell_request_submitted"] is True
    assert opened == [str(target.resolve())]


def test_read_text_file_returns_bounded_text(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("linha 1\nlinha 2", encoding="utf-8")

    result = ReadTextFileAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_file",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["content"] == "linha 1\nlinha 2"
    assert result.evidence["text"] is True
    assert result.evidence["truncated"] is False
    assert result.evidence["content_is_untrusted_data"] is True


def test_read_text_file_normalizes_windows_newlines(tmp_path: Path) -> None:
    target = tmp_path / "windows.txt"
    target.write_bytes(b"line 1\r\nline 2\rline 3\n")

    result = ReadTextFileAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_file",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["content"] == "line 1\nline 2\nline 3\n"

def test_read_text_file_truncates_at_global_limit(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_bytes(b"a" * (MAX_READ_BYTES + 50))

    result = ReadTextFileAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_file",
            arguments={"path": str(target)},
        )
    )

    assert result.success is True
    assert result.evidence["bytes_read"] == MAX_READ_BYTES
    assert result.evidence["truncated"] is True
    assert len(result.evidence["content"]) == MAX_READ_BYTES


def test_read_text_file_rejects_binary_data(tmp_path: Path) -> None:
    target = tmp_path / "binary.bin"
    target.write_bytes(b"abc\x00def")

    result = ReadTextFileAction(WindowsFileSystemAdapter()).execute(
        ActionRequest(
            action="read_text_file",
            arguments={"path": str(target)},
        )
    )

    assert result.success is False
    assert result.error_code == "FILE_NOT_TEXT"
    assert result.evidence["text"] is False


def test_read_text_file_always_requires_confirmation() -> None:
    normal = ActionRequest(
        action="read_text_file",
        arguments={"path": r"C:\Temp\notes.txt"},
    )
    sensitive = ActionRequest(
        action="read_text_file",
        arguments={"path": r"C:\Projetos\TheOS\The-OS\.env"},
    )
    private_key = ActionRequest(
        action="read_text_file",
        arguments={"path": r"C:\Temp\server.pem"},
    )

    assert ReadTextFileAction.risk_for(normal) is ActionRisk.CONFIRM
    assert ReadTextFileAction.risk_for(sensitive) is ActionRisk.PRIVILEGED
    assert ReadTextFileAction.risk_for(private_key) is ActionRisk.PRIVILEGED
