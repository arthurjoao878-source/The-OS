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
from theos.core.actions.git_local import GitCommitStagedFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    FIXED_GIT_COMMIT_MESSAGE,
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
        "commit_message": FIXED_GIT_COMMIT_MESSAGE,
        "target_index_status": "M",
        "target_worktree_status": " ",
        "staged_paths_observed": 1,
    }


def test_git_commit_catalog_has_no_model_arguments() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_commit_staged_file"]

    assert len(definitions) == 56
    assert definition.parameters["properties"] == {}
    assert definition.parameters["additionalProperties"] is False
    assert "Não aceita argumentos" in definition.description
    assert "mensagem é fixa" in definition.description
    assert "Nenhum push" in definition.description

    request = catalog.build_action_request(
        ToolCall(name="git_commit_staged_file", arguments={})
    )
    assert request.arguments == {}

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="git_commit_staged_file",
                arguments={"message": "model controlled"},
            )
        )


def test_git_commit_preview_requires_exactly_one_staged_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "repository_root": str(tmp_path),
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )
    monkeypatch.setattr(
        adapter,
        "_staged_paths",
        lambda _git: (["README.md", "other.py"], None),
    )

    evidence = adapter.preview_commit_staged_file()

    assert evidence["error"] == "GIT_COMMIT_REQUIRES_SINGLE_STAGED_PATH"
    assert evidence["staged_paths_observed"] == 2


def test_git_commit_preview_requires_tracked_staged_modification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "repository_root": str(tmp_path),
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("A", " "), None),
    )

    evidence = adapter.preview_commit_staged_file()

    assert evidence["error"] == "GIT_COMMIT_TARGET_NOT_STAGED_TRACKED_MODIFICATION"


def test_git_commit_preview_binds_path_target_head_git_and_fixed_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "repository_root": str(tmp_path),
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
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _path: _preview())

    evidence = adapter.preview_commit_staged_file()

    assert "error" not in evidence
    assert evidence["path"] == "README.md"
    assert evidence["target_sha256"] == "b" * 64
    assert evidence["head_sha"] == "a" * 40
    assert evidence["git_executable_sha256"] == "c" * 64
    assert evidence["commit_message"] == FIXED_GIT_COMMIT_MESSAGE
    assert evidence["model_commit_message_authority"] is False
    assert evidence["hooks_disabled"] is True
    assert evidence["gpg_signing_disabled"] is True


def test_git_commit_blocks_preview_guard_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_commit_staged_file",
        lambda: _preview(target_sha="d" * 64),
    )

    evidence = adapter.commit_staged_file(
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
        expected_commit_message=FIXED_GIT_COMMIT_MESSAGE,
    )

    assert evidence["error"] == "GIT_COMMIT_TARGET_CHANGED_AFTER_PREVIEW"


def test_git_commit_success_verifies_exact_local_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_commit_staged_file", lambda: _preview())
    calls = []

    def fake_commit(_git, args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(adapter, "_run_git_commit", fake_commit)
    reads = {"HEAD": "d" * 40, "HEAD^": "a" * 40}
    monkeypatch.setattr(
        adapter,
        "_read_revision_sha",
        lambda _git, rev: (reads[rev], None),
    )
    monkeypatch.setattr(adapter, "_commit_paths", lambda _git: (["README.md"], None))
    monkeypatch.setattr(
        adapter,
        "_commit_subject",
        lambda _git: (FIXED_GIT_COMMIT_MESSAGE, None),
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_target_clean_after_commit",
        lambda _git, _path: (True, None),
    )
    monkeypatch.setattr(
        adapter,
        "_current_target_identity",
        lambda _path: {
            "path": "README.md",
            "target_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )

    evidence = adapter.commit_staged_file(
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
        expected_commit_message=FIXED_GIT_COMMIT_MESSAGE,
    )

    assert calls == [
        [
            "commit",
            "--no-gpg-sign",
            "-m",
            FIXED_GIT_COMMIT_MESSAGE,
        ]
    ]
    assert "error" not in evidence
    assert evidence["committed_path"] == "README.md"
    assert evidence["commit_sha"] == "d" * 40
    assert evidence["parent_sha"] == "a" * 40
    assert evidence["committed_paths_observed"] == 1
    assert evidence["index_empty"] is True
    assert evidence["target_unchanged"] is True
    assert evidence["target_clean"] is True
    assert evidence["git_remote_authority"] is False
    assert evidence["rollback_authority"] is False


def test_git_commit_failure_with_unchanged_head_does_not_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_commit_staged_file", lambda: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_commit",
        lambda _git, args: subprocess.CompletedProcess(args, 1, b"", b"fail"),
    )
    monkeypatch.setattr(
        adapter,
        "_read_revision_sha",
        lambda _git, _rev: ("a" * 40, None),
    )

    evidence = adapter.commit_staged_file(
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
        expected_commit_message=FIXED_GIT_COMMIT_MESSAGE,
    )

    assert evidence["error"] == "GIT_COMMIT_FAILED"
    assert evidence["rollback_authority"] is False


def test_git_commit_failure_after_head_change_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_commit_staged_file", lambda: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_commit",
        lambda _git, args: subprocess.CompletedProcess(args, 1, b"", b"fail"),
    )
    monkeypatch.setattr(
        adapter,
        "_read_revision_sha",
        lambda _git, _rev: ("d" * 40, None),
    )

    evidence = adapter.commit_staged_file(
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
        expected_commit_message=FIXED_GIT_COMMIT_MESSAGE,
    )

    assert evidence["error"] == "GIT_COMMIT_STATE_AMBIGUOUS_AFTER_FAILURE"
    assert evidence["head_after_failure"] == "d" * 40


def test_git_commit_postcondition_failure_never_rewrites_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_commit_staged_file", lambda: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_commit",
        lambda _git, args: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    reads = {"HEAD": "d" * 40, "HEAD^": "a" * 40}
    monkeypatch.setattr(
        adapter,
        "_read_revision_sha",
        lambda _git, rev: (reads[rev], None),
    )
    monkeypatch.setattr(adapter, "_commit_paths", lambda _git: (["other.py"], None))
    monkeypatch.setattr(
        adapter,
        "_commit_subject",
        lambda _git: (FIXED_GIT_COMMIT_MESSAGE, None),
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_target_clean_after_commit",
        lambda _git, _path: (True, None),
    )
    monkeypatch.setattr(
        adapter,
        "_current_target_identity",
        lambda _path: {
            "path": "README.md",
            "target_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )

    evidence = adapter.commit_staged_file(
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
        expected_commit_message=FIXED_GIT_COMMIT_MESSAGE,
    )

    assert evidence["error"] == "GIT_COMMIT_POSTCONDITION_FAILED"
    assert evidence["rollback_authority"] is False


class _PreviewAdapter:
    @staticmethod
    def preview_commit_staged_file():
        return _preview()


def test_git_commit_action_preview_binds_fixed_commit_and_is_destructive() -> None:
    action = GitCommitStagedFileAction(_PreviewAdapter())
    request = ActionRequest(action="git_commit_staged_file", arguments={})
    preview = action.confirmation_preview(request)

    assert action.risk is ActionRisk.DESTRUCTIVE
    assert preview.allowed is True
    assert preview.execution_guard["_expected_git_commit_path"] == "README.md"
    assert (
        preview.execution_guard["_expected_git_commit_target_sha256"]
        == "b" * 64
    )
    assert preview.execution_guard["_expected_git_commit_head_sha256"] == "a" * 40
    assert (
        preview.execution_guard["_expected_git_commit_message"]
        == FIXED_GIT_COMMIT_MESSAGE
    )
    assert "hooksPath temporário vazio" in preview.text
    assert "assinatura GPG é desabilitada" in preview.text
    assert "Nenhum push" in preview.text
    assert "rollback automático" in preview.text


def test_git_commit_action_registration_and_missing_preview_guard() -> None:
    class _NoRunAdapter:
        def commit_staged_file(self, **kwargs):
            _ = kwargs
            raise AssertionError("commit must not run")

    missing = GitCommitStagedFileAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_commit_staged_file", arguments={})
    )
    assert missing.success is False
    assert missing.error_code == "GIT_COMMIT_PREVIEW_REQUIRED"

    registry = build_action_registry()
    request = ActionRequest(action="git_commit_staged_file", arguments={})
    assert registry.contains("git_commit_staged_file") is True
    assert registry.risk_for(request) is ActionRisk.DESTRUCTIVE


class _CommitProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_commit_staged_file",
                    arguments={},
                    call_id="git_commit_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Commit recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_commit_gate_and_progress() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Commit concluído.",
        )

    registry.register(
        GitCommitStagedFileAction.name,
        handler,
        risk=GitCommitStagedFileAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _CommitProvider(),
        registry,
        catalog,
    ).execute(
        "Crie o commit local.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []

    message = ToolLoopExecutor._progress_message(
        ActionRequest(action="git_commit_staged_file", arguments={})
    )
    assert message == "Criando commit Git local do único arquivo staged..."
