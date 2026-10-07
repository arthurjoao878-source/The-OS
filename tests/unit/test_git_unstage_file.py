from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.git_local import GitUnstageFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import (
    ToolCall,
    ToolValidationError,
    build_default_tool_catalog,
)
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    MAX_GIT_UNSTAGE_FILE_BYTES,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _preview(
    *,
    path: str = "README.md",
    target_sha: str = "b" * 64,
    head_sha: str = "a" * 40,
    git_path: str = r"C:\Git\git.exe",
    git_sha: str = "c" * 64,
) -> dict[str, object]:
    return {
        "repository_root": r"C:\Repo",
        "path": path,
        "target_sha256": target_sha,
        "file_size_bytes": 7,
        "head_sha": head_sha,
        "git_executable_path": git_path,
        "git_executable_sha256": git_sha,
        "index_contains_only_target": True,
        "target_index_status": "M",
        "target_worktree_status": " ",
        "tracked_existing_file_required": True,
    }


def test_git_unstage_catalog_is_single_repo_relative_path() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_unstage_file"]

    assert len(definitions) == 60
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "índice precisa conter somente esse arquivo" in definition.description
    assert "git reset --quiet HEAD -- <path>" in definition.description

    request = catalog.build_action_request(
        ToolCall(
            name="git_unstage_file",
            arguments={"path": r" src\theos\bootstrap.py "},
        )
    )
    assert request.arguments == {"path": "src/theos/bootstrap.py"}

    for invalid in (
        r"C:\Repo\README.md",
        "../README.md",
        "/README.md",
        "src//file.py",
        "src/./file.py",
        "bad\nname.py",
        "name:stream",
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(name="git_unstage_file", arguments={"path": invalid})
            )


def test_git_unstage_preview_requires_exact_single_staged_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "_staged_paths",
        lambda _git: (["README.md", "other.py"], None),
    )

    evidence = adapter.preview_unstage_target("README.md")

    assert evidence["error"] == "GIT_UNSTAGE_REQUIRES_ONLY_TARGET_STAGED"
    assert evidence["staged_paths_observed"] == 2


def test_git_unstage_preview_requires_staged_tracked_modification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", "M"), None),
    )

    evidence = adapter.preview_unstage_target("README.md")

    assert evidence["error"] == "GIT_UNSTAGE_TARGET_NOT_STAGED_MODIFICATION"


def test_git_unstage_preview_binds_target_head_and_git_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", " "), None),
    )

    evidence = adapter.preview_unstage_target("README.md")

    assert "error" not in evidence
    assert evidence["path"] == "README.md"
    assert evidence["target_sha256"] == "b" * 64
    assert evidence["head_sha"] == "a" * 40
    assert evidence["git_executable_sha256"] == "c" * 64
    assert evidence["index_contains_only_target"] is True
    assert evidence["target_index_status"] == "M"
    assert evidence["target_worktree_status"] == " "
    assert evidence["max_unstage_file_bytes"] == MAX_GIT_UNSTAGE_FILE_BYTES


def test_git_unstage_blocks_preview_guard_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_unstage_target",
        lambda _raw: _preview(target_sha="d" * 64),
    )

    evidence = adapter.unstage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_UNSTAGE_TARGET_CHANGED_AFTER_PREVIEW"


def test_git_unstage_success_verifies_empty_index_and_unstaged_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_unstage_target", lambda _raw: _preview())
    calls = []

    def fake_mutating(_git, args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(adapter, "_run_git_mutating", fake_mutating)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: ((" ", "M"), None),
    )

    evidence = adapter.unstage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert calls == [["reset", "--quiet", "HEAD", "--", "README.md"]]
    assert "error" not in evidence
    assert evidence["unstaged_path"] == "README.md"
    assert evidence["staged_paths_observed"] == 0
    assert evidence["index_only_mutation_verified"] is True
    assert evidence["target_unchanged"] is True
    assert evidence["head_unchanged"] is True
    assert evidence["git_executable_unchanged"] is True
    assert evidence["git_remote_authority"] is False
    assert evidence["commit_authority"] is False


def test_git_unstage_failed_reset_attempts_same_path_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_unstage_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(args, 1, b"", b"fail"),
    )
    rollbacks = []
    monkeypatch.setattr(
        adapter,
        "_rollback_unstage_target",
        lambda _git, path: rollbacks.append(path) or True,
    )

    evidence = adapter.unstage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_UNSTAGE_FAILED"
    assert evidence["rollback_verified"] is True
    assert rollbacks == ["README.md"]


def test_git_unstage_postcondition_failure_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_unstage_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", " "), None),
    )
    monkeypatch.setattr(
        adapter,
        "_rollback_unstage_target",
        lambda _git, _path: True,
    )

    evidence = adapter.unstage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_UNSTAGE_POSTCONDITION_FAILED"
    assert evidence["rollback_verified"] is True


def test_git_unstage_rollback_verifies_single_staged_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", " "), None),
    )

    assert adapter._rollback_unstage_target(Path("git.exe"), "README.md") is True


class _PreviewAdapter:
    @staticmethod
    def preview_unstage_target(_raw):
        return _preview()


def test_git_unstage_action_preview_binds_guard_and_warns_index_mutation() -> None:
    preview = GitUnstageFileAction(_PreviewAdapter()).confirmation_preview(
        ActionRequest(action="git_unstage_file", arguments={"path": "README.md"})
    )

    assert preview.allowed is True
    assert preview.execution_guard["_expected_git_unstage_path"] == "README.md"
    assert preview.execution_guard["_expected_git_unstage_target_sha256"] == "b" * 64
    assert preview.execution_guard["_expected_git_unstage_head_sha256"] == "a" * 40
    assert "modificará somente o índice Git" in preview.text
    assert "git reset --quiet HEAD -- <path>" in preview.text
    assert "git add -- <path>" in preview.text
    assert "commit" in preview.text
    assert "push" in preview.text


def test_git_unstage_action_policy_and_registration() -> None:
    class _NoRunAdapter:
        def unstage_file(self, *args, **kwargs):
            _ = args, kwargs
            raise AssertionError("unstage must not run")

    missing_preview = GitUnstageFileAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_unstage_file", arguments={"path": "README.md"})
    )
    assert missing_preview.success is False
    assert missing_preview.error_code == "GIT_UNSTAGE_PREVIEW_REQUIRED"

    registry = build_action_registry()
    ordinary = ActionRequest(action="git_unstage_file", arguments={"path": "README.md"})
    sensitive = ActionRequest(action="git_unstage_file", arguments={"path": ".env"})

    assert registry.contains("git_unstage_file") is True
    assert registry.risk_for(ordinary) is ActionRisk.CONFIRM
    assert registry.risk_for(sensitive) is ActionRisk.PRIVILEGED


class _UnstageProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_unstage_file",
                    arguments={"path": "README.md"},
                    call_id="git_unstage_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Unstage recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_unstage_gate_and_progress() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Unstage Git concluído.",
        )

    registry.register(
        GitUnstageFileAction.name,
        handler,
        risk=GitUnstageFileAction.risk_for,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _UnstageProvider(),
        registry,
        catalog,
    ).execute(
        "Remova README.md do stage.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []

    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="git_unstage_file",
            arguments={"path": "README.md"},
        )
    )
    assert message == "Removendo stage Git de README.md..."
