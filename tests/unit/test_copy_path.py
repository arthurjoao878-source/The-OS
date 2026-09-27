from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import CopyPathAction
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.windows.file_system import WindowsFileSystemAdapter


def _approve(action: CopyPathAction, request: ActionRequest) -> None:
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)


def test_copy_file_requires_preview_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "copy.txt"
    source.write_text("copy me\n", encoding="utf-8")

    action = CopyPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "MUTATION_PREVIEW_REQUIRED"
    assert destination.exists() is False

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "COPIAR ARQUIVO" in preview.text
    assert "\\n" not in preview.text
    assert "\nOrigem:" in preview.text
    assert "\nDestino:" in preview.text
    request.arguments.update(preview.execution_guard)

    result = action.execute(request)

    assert result.success is True
    assert result.evidence["copy_verified"] is True
    assert result.evidence["source_preserved"] is True
    assert source.read_text(encoding="utf-8") == "copy me\n"
    assert destination.read_text(encoding="utf-8") == "copy me\n"


def test_copy_directory_tree_is_recursive_and_verified(tmp_path: Path) -> None:
    source = tmp_path / "source-dir"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "one.txt").write_text("one", encoding="utf-8")
    (nested / "two.txt").write_text("two", encoding="utf-8")
    destination = tmp_path / "copied-dir"

    action = CopyPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )
    _approve(action, request)
    result = action.execute(request)

    assert result.success is True
    assert result.evidence["kind"] == "directory"
    assert result.evidence["files"] == 2
    assert result.message.startswith("Pasta copiada para ")
    assert source.is_dir()
    assert (destination / "one.txt").read_text(encoding="utf-8") == "one"
    assert (destination / "nested" / "two.txt").read_text(encoding="utf-8") == "two"


def test_copy_never_overwrites_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("source", encoding="utf-8")
    destination.write_text("keep", encoding="utf-8")

    action = CopyPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )

    preview = action.confirmation_preview(request)

    assert preview.allowed is False
    assert "DESTINATION_ALREADY_EXISTS" in preview.text
    assert destination.read_text(encoding="utf-8") == "keep"


def test_copy_blocks_if_source_changes_after_preview(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_text("before", encoding="utf-8")

    action = CopyPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )
    _approve(action, request)

    source.write_text("changed after preview", encoding="utf-8")
    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "COPY_CHANGED_OR_VERIFICATION_FAILED"
    assert destination.exists() is False


def test_sensitive_copy_is_privileged(tmp_path: Path) -> None:
    source = tmp_path / ".env"
    destination = tmp_path / "backup.env"
    source.write_text("SECRET=value", encoding="utf-8")

    action = CopyPathAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="copy_path",
        arguments={
            "source": str(source),
            "destination": str(destination),
        },
    )

    assert action.risk_for(request) is ActionRisk.PRIVILEGED


def test_catalog_builds_copy_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="copy_path",
            arguments={
                "source": r" C:\Temp\a.txt ",
                "destination": r" C:\Temp\b.txt ",
            },
        )
    )

    assert request.action == "copy_path"
    assert request.arguments == {
        "source": r"C:\Temp\a.txt",
        "destination": r"C:\Temp\b.txt",
    }
