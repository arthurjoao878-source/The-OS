from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import (
    CreateDirectoryAction,
    MovePathAction,
    TrashPathAction,
)
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.windows.file_system import WindowsFileSystemAdapter


def _approve(action, request: ActionRequest) -> None:
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)


def test_create_directory_requires_preview_guard(tmp_path: Path) -> None:
    target = tmp_path / "created"
    action = CreateDirectoryAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="create_directory",
        arguments={"path": str(target)},
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MUTATION_PREVIEW_REQUIRED"
    assert target.exists() is False

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "CRIAR PASTA" in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert target.is_dir()


def test_move_path_is_destructive_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "before.txt"
    destination = tmp_path / "after.txt"
    source.write_text("hello", encoding="utf-8")

    action = MovePathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="move_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE
    preview = action.confirmation_preview(request)
    assert preview.allowed is True

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert source.exists() is False
    assert destination.read_text(encoding="utf-8") == "hello"

    occupied = tmp_path / "occupied.txt"
    occupied.write_text("keep", encoding="utf-8")
    second = ActionRequest(
        action="move_path",
        arguments={
            "source": str(destination),
            "destination": str(occupied),
        },
    )
    blocked = action.confirmation_preview(second)

    assert blocked.allowed is False
    assert "DESTINATION_ALREADY_EXISTS" in blocked.text
    assert occupied.read_text(encoding="utf-8") == "keep"


def test_move_blocks_if_source_changes_after_preview(tmp_path: Path) -> None:
    source = tmp_path / "before.txt"
    destination = tmp_path / "after.txt"
    source.write_text("one", encoding="utf-8")

    action = MovePathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="move_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )
    _approve(action, request)

    source.write_text("changed and longer", encoding="utf-8")
    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "MUTATION_CHANGED_AFTER_PREVIEW"
    assert source.exists() is True
    assert destination.exists() is False


def test_trash_path_uses_recycle_adapter_and_verifies_absence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "trash-me.txt"
    target.write_text("temporary", encoding="utf-8")

    def fake_recycle(path: Path) -> tuple[int, bool]:
        path.unlink()
        return 0, False

    monkeypatch.setattr(
        "theos.integrations.windows.file_system._recycle_with_shell",
        fake_recycle,
    )

    action = TrashPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="trash_path",
        arguments={"path": str(target)},
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "LIXEIRA" in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert result.evidence["sent_to_recycle_bin"] is True
    assert target.exists() is False


def test_sensitive_move_and_trash_are_privileged(tmp_path: Path) -> None:
    sensitive = tmp_path / ".env"
    sensitive.write_text("SECRET=value", encoding="utf-8")
    destination = tmp_path / "renamed.env"

    move = MovePathAction(WindowsFileSystemAdapter())
    trash = TrashPathAction(WindowsFileSystemAdapter())

    assert move.risk_for(
        ActionRequest(
            action="move_path",
            arguments={
                "source": str(sensitive),
                "destination": str(destination),
            },
        )
    ) is ActionRisk.PRIVILEGED
    assert trash.risk_for(
        ActionRequest(
            action="trash_path",
            arguments={"path": str(sensitive)},
        )
    ) is ActionRisk.PRIVILEGED


def test_catalog_builds_path_mutation_requests() -> None:
    catalog = build_default_tool_catalog()

    create = catalog.build_action_request(
        ToolCall(
            name="create_directory",
            arguments={"path": r" C:\Temp\NewFolder "},
        )
    )
    move = catalog.build_action_request(
        ToolCall(
            name="move_path",
            arguments={
                "source": r" C:\Temp\a.txt ",
                "destination": r" C:\Temp\b.txt ",
            },
        )
    )
    trash = catalog.build_action_request(
        ToolCall(
            name="trash_path",
            arguments={"path": r" C:\Temp\b.txt "},
        )
    )

    assert create.arguments == {"path": r"C:\Temp\NewFolder"}
    assert move.arguments == {
        "source": r"C:\Temp\a.txt",
        "destination": r"C:\Temp\b.txt",
    }
    assert trash.arguments == {"path": r"C:\Temp\b.txt"}
