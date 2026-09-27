from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.file_system import WriteTextFileAction
from theos.integrations.windows.file_system import WindowsFileSystemAdapter


def _approve_preview(
    action: WriteTextFileAction,
    request: ActionRequest,
) -> None:
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)


def test_write_new_text_file_requires_preview_guard(tmp_path: Path) -> None:
    target = tmp_path / "created.txt"
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="write_text_file",
        arguments={"path": str(target), "content": "hello\nworld\n"},
    )

    assert action.risk_for(request) is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "WRITE_PREVIEW_REQUIRED"
    assert target.exists() is False

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "CRIAR NOVO ARQUIVO" in preview.text
    assert "+hello" in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert result.evidence["atomic_replace"] is True
    assert result.evidence["write_verified"] is True
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"


def test_overwrite_text_file_is_destructive_and_has_diff(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old\n", encoding="utf-8")
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="write_text_file",
        arguments={"path": str(target), "content": "new\n"},
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "SUBSTITUIR ARQUIVO" in preview.text
    assert "-old" in preview.text
    assert "+new" in preview.text

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "new\n"


def test_sensitive_write_is_privileged_and_preview_is_redacted(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    target.write_text("OLD_SECRET=one\n", encoding="utf-8")
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="write_text_file",
        arguments={"path": str(target), "content": "NEW_SECRET=two\n"},
    )

    assert action.risk_for(request) is ActionRisk.PRIVILEGED
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "conteúdo ocultada" in preview.text.casefold()
    assert "OLD_SECRET" not in preview.text
    assert "NEW_SECRET" not in preview.text


def test_write_blocks_if_target_changes_after_preview(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("before\n", encoding="utf-8")
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="write_text_file",
        arguments={"path": str(target), "content": "approved\n"},
    )

    _approve_preview(action, request)
    target.write_text("changed elsewhere\n", encoding="utf-8")

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "FILE_CHANGED_AFTER_PREVIEW"
    assert target.read_text(encoding="utf-8") == "changed elsewhere\n"


def test_write_preview_rejects_large_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_bytes(b"a" * (16 * 1024 + 1))
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    request = ActionRequest(
        action="write_text_file",
        arguments={"path": str(target), "content": "small"},
    )

    preview = action.confirmation_preview(request)

    assert preview.allowed is False
    assert "EXISTING_FILE_TOO_LARGE" in preview.text
