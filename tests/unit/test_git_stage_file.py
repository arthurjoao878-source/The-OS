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
from theos.core.actions.git_local import GitStageFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import (
    ToolCall,
    ToolValidationError,
    build_default_tool_catalog,
)
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    MAX_GIT_STAGE_FILE_BYTES,
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
        "index_empty": True,
        "target_index_status": " ",
        "target_worktree_status": "M",
        "tracked_existing_file_required": True,
    }


def test_git_stage_catalog_is_single_repo_relative_path() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_stage_file"]

    assert len(definitions) == 53
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False
    assert "índice precisa estar vazio" in definition.description
    assert "arquivos novos" in definition.description

    request = catalog.build_action_request(
        ToolCall(
            name="git_stage_file",
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
                ToolCall(name="git_stage_file", arguments={"path": invalid})
            )


def test_git_stage_mutation_environment_scrubs_git_and_keeps_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_DIR", r"C:\Elsewhere")
    adapter = WindowsLocalGitAdapter(tmp_path)
    environment = adapter._controlled_mutation_environment()

    assert "GIT_DIR" not in environment
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_PAGER"] == "cat"
    assert environment["NO_COLOR"] == "1"
    assert "GIT_OPTIONAL_LOCKS" not in environment


def test_git_stage_mutating_runner_uses_fixed_no_shell_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    git_exe = tmp_path / "git.exe"
    git_exe.write_bytes(b"git")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = adapter._run_git_mutating(git_exe, ["add", "--", "README.md"])

    assert result.returncode == 0
    assert captured["argv"] == [
        str(git_exe),
        "-C",
        str(repo.resolve()),
        "add",
        "--",
        "README.md",
    ]
    assert captured["shell"] is False
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_OPTIONAL_LOCKS" not in captured["env"]


def test_git_stage_preview_requires_empty_global_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "_staged_paths",
        lambda _git: (["other.py"], None),
    )

    evidence = adapter.preview_stage_target("README.md")

    assert evidence["error"] == "GIT_STAGE_REQUIRES_EMPTY_INDEX"
    assert evidence["staged_paths_observed"] == 1


def test_git_stage_preview_requires_unstaged_tracked_modification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", " "), None),
    )

    evidence = adapter.preview_stage_target("README.md")

    assert evidence["error"] == "GIT_STAGE_TARGET_NOT_UNSTAGED_MODIFICATION"


def test_git_stage_preview_binds_target_head_and_git_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_diff_target", lambda _raw: _preview())
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: ((" ", "M"), None),
    )

    evidence = adapter.preview_stage_target("README.md")

    assert "error" not in evidence
    assert evidence["path"] == "README.md"
    assert evidence["target_sha256"] == "b" * 64
    assert evidence["head_sha"] == "a" * 40
    assert evidence["git_executable_sha256"] == "c" * 64
    assert evidence["index_empty"] is True
    assert evidence["target_index_status"] == " "
    assert evidence["target_worktree_status"] == "M"
    assert evidence["max_stage_file_bytes"] == MAX_GIT_STAGE_FILE_BYTES


def test_git_stage_blocks_preview_guard_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_stage_target",
        lambda _raw: _preview(target_sha="d" * 64),
    )

    evidence = adapter.stage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_STAGE_TARGET_CHANGED_AFTER_PREVIEW"


def test_git_stage_success_verifies_exact_single_index_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    before = _preview()
    monkeypatch.setattr(adapter, "preview_stage_target", lambda _raw: before)
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(
            args, 0, stdout=b"", stderr=b"warning"
        ),
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
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", " "), None),
    )
    monkeypatch.setattr(
        adapter,
        "_staged_paths",
        lambda _git: (["README.md"], None),
    )

    evidence = adapter.stage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert "error" not in evidence
    assert evidence["staged_path"] == "README.md"
    assert evidence["staged_paths_observed"] == 1
    assert evidence["index_only_mutation_verified"] is True
    assert evidence["target_unchanged"] is True
    assert evidence["head_unchanged"] is True
    assert evidence["git_executable_unchanged"] is True
    assert evidence["git_remote_authority"] is False
    assert evidence["commit_authority"] is False


def test_git_stage_failed_add_attempts_same_path_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_stage_target", lambda _raw: _preview())
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(args, 1, b"", b"fail"),
    )
    rollbacks = []
    monkeypatch.setattr(
        adapter,
        "_rollback_stage_target",
        lambda _git, path: rollbacks.append(path) or True,
    )

    evidence = adapter.stage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_STAGE_FAILED"
    assert evidence["rollback_verified"] is True
    assert rollbacks == ["README.md"]


def test_git_stage_postcondition_failure_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_stage_target", lambda _raw: _preview())
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
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: (("M", "M"), None),
    )
    monkeypatch.setattr(
        adapter,
        "_staged_paths",
        lambda _git: (["README.md"], None),
    )
    monkeypatch.setattr(
        adapter,
        "_rollback_stage_target",
        lambda _git, _path: True,
    )

    evidence = adapter.stage_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_STAGE_POSTCONDITION_FAILED"
    assert evidence["rollback_verified"] is True


def test_git_stage_rollback_verifies_empty_index_and_unstaged_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "_run_git_mutating",
        lambda _git, args: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_staged_paths", lambda _git: ([], None))
    monkeypatch.setattr(
        adapter,
        "_stage_target_status",
        lambda _git, _path: ((" ", "M"), None),
    )

    assert adapter._rollback_stage_target(Path("git.exe"), "README.md") is True


class _PreviewAdapter:
    @staticmethod
    def preview_stage_target(_raw):
        return _preview()


def test_git_stage_action_preview_binds_guard_and_warns_index_mutation() -> None:
    preview = GitStageFileAction(_PreviewAdapter()).confirmation_preview(
        ActionRequest(action="git_stage_file", arguments={"path": "README.md"})
    )

    assert preview.allowed is True
    assert preview.execution_guard["_expected_git_stage_path"] == "README.md"
    assert preview.execution_guard["_expected_git_stage_target_sha256"] == "b" * 64
    assert preview.execution_guard["_expected_git_stage_head_sha256"] == "a" * 40
    assert "modificará somente o índice Git" in preview.text
    assert "git add --" in preview.text
    assert "commit" in preview.text
    assert "push" in preview.text


def test_git_stage_action_risk_escalates_sensitive_names() -> None:
    ordinary = ActionRequest(action="git_stage_file", arguments={"path": "README.md"})
    sensitive = ActionRequest(action="git_stage_file", arguments={"path": ".env"})

    assert GitStageFileAction.risk_for(ordinary) is ActionRisk.CONFIRM
    assert GitStageFileAction.risk_for(sensitive) is ActionRisk.PRIVILEGED


def test_git_stage_execute_requires_approved_preview() -> None:
    class _NoRunAdapter:
        def stage_file(self, *args, **kwargs):
            _ = args, kwargs
            raise AssertionError("stage must not run")

    result = GitStageFileAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_stage_file", arguments={"path": "README.md"})
    )

    assert result.success is False
    assert result.error_code == "GIT_STAGE_PREVIEW_REQUIRED"


def test_bootstrap_registers_git_stage_file_action() -> None:
    registry = build_action_registry()
    ordinary = ActionRequest(action="git_stage_file", arguments={"path": "README.md"})
    sensitive = ActionRequest(action="git_stage_file", arguments={"path": ".env"})

    assert registry.contains("git_stage_file") is True
    assert registry.risk_for(ordinary) is ActionRisk.CONFIRM
    assert registry.risk_for(sensitive) is ActionRisk.PRIVILEGED


class _StageProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_stage_file",
                    arguments={"path": "README.md"},
                    call_id="git_stage_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Stage recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_stage_gate_does_not_mutate_before_confirmation() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Stage Git concluído.",
        )

    registry.register(
        GitStageFileAction.name,
        handler,
        risk=GitStageFileAction.risk_for,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _StageProvider(),
        registry,
        catalog,
    ).execute(
        "Prepare README.md no stage.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_git_stage_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="git_stage_file",
            arguments={"path": "README.md"},
        )
    )

    assert message == "Preparando stage Git de README.md..."
