from __future__ import annotations

import hashlib
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
from theos.core.actions.git_local import GitDiffFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import (
    ToolCall,
    ToolValidationError,
    build_default_tool_catalog,
)
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    MAX_GIT_DIFF_FILE_BYTES,
    MAX_GIT_DIFF_LINES,
    MAX_GIT_DIFF_OUTPUT_BYTES,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _target(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "README.md"
    target.write_text("changed\n", encoding="utf-8")
    git_exe = tmp_path / "git.exe"
    git_exe.write_bytes(b"M84_GIT")
    return repo, target, git_exe


def _install_preview_git(
    adapter: WindowsLocalGitAdapter,
    repo: Path,
    target: Path,
    git_exe: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    git_hash = hashlib.sha256(git_exe.read_bytes()).hexdigest()
    monkeypatch.setattr(
        WindowsLocalGitAdapter,
        "_git_executable",
        staticmethod(lambda: git_exe),
    )

    def fake_run(_git, arguments):
        if arguments == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=str(repo.resolve()).encode("utf-8"),
                stderr=b"",
            )
        if arguments == ["rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"a" * 40,
                stderr=b"",
            )
        if arguments[:2] == ["ls-files", "--error-unmatch"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"README.md\n",
                stderr=b"",
            )
        if arguments[:2] == ["diff", "--quiet"]:
            return subprocess.CompletedProcess(arguments, 1, stdout=b"", stderr=b"")
        raise AssertionError(arguments)

    monkeypatch.setattr(adapter, "_run_git", fake_run)
    return git_hash


def test_git_diff_catalog_is_single_repo_relative_path() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_diff_file"]

    assert len(definitions) == 61
    assert set(definition.parameters["properties"]) == {"path"}
    assert set(definition.parameters["required"]) == {"path"}
    assert definition.parameters["additionalProperties"] is False

    request = catalog.build_action_request(
        ToolCall(
            name="git_diff_file",
            arguments={"path": r" src\theos\core\actions\git_local.py "},
        )
    )
    assert request.arguments == {
        "path": "src/theos/core/actions/git_local.py"
    }

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
                ToolCall(
                    name="git_diff_file",
                    arguments={"path": invalid},
                )
            )


def test_git_diff_preview_hashes_target_and_binds_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, target, git_exe = _target(tmp_path)
    adapter = WindowsLocalGitAdapter(repo)
    git_hash = _install_preview_git(
        adapter,
        repo,
        target,
        git_exe,
        monkeypatch,
    )

    evidence = adapter.preview_diff_target("README.md")

    assert evidence["path"] == "README.md"
    assert evidence["file_size_bytes"] == target.stat().st_size
    assert evidence["target_sha256"] == hashlib.sha256(
        target.read_bytes()
    ).hexdigest()
    assert evidence["head_sha"] == "a" * 40
    assert evidence["git_executable_sha256"] == git_hash
    assert evidence["diff_content_returned"] is False


def test_git_diff_preview_rejects_absolute_traversal_and_link_like(
    tmp_path: Path,
) -> None:
    repo, _, _ = _target(tmp_path)
    adapter = WindowsLocalGitAdapter(repo)

    assert adapter.preview_diff_target("../README.md")["error"] == (
        "GIT_DIFF_PATH_INVALID"
    )
    assert adapter.preview_diff_target(r"C:\Repo\README.md")["error"] == (
        "GIT_DIFF_PATH_INVALID"
    )


def test_git_diff_preview_rejects_binary_and_oversized(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    binary = repo / "binary.dat"
    binary.write_bytes(b"a\0b")
    large = repo / "large.txt"
    large.write_bytes(b"x" * (MAX_GIT_DIFF_FILE_BYTES + 1))
    adapter = WindowsLocalGitAdapter(repo)

    assert adapter.preview_diff_target("binary.dat")["error"] == (
        "GIT_DIFF_BINARY_NOT_ALLOWED"
    )
    assert adapter.preview_diff_target("large.txt")["error"] == (
        "GIT_DIFF_FILE_TOO_LARGE"
    )


def test_git_diff_preview_requires_tracked_changed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, target, git_exe = _target(tmp_path)
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(
        WindowsLocalGitAdapter,
        "_git_executable",
        staticmethod(lambda: git_exe),
    )

    def fake_untracked(_git, arguments):
        if arguments == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(
                arguments, 0, stdout=str(repo.resolve()).encode(), stderr=b""
            )
        if arguments == ["rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"a" * 40, stderr=b""
            )
        if arguments[:2] == ["ls-files", "--error-unmatch"]:
            return subprocess.CompletedProcess(arguments, 1, stdout=b"", stderr=b"")
        raise AssertionError(arguments)

    monkeypatch.setattr(adapter, "_run_git", fake_untracked)
    evidence = adapter.preview_diff_target(target.name)
    assert evidence["error"] == "GIT_DIFF_TRACKED_FILE_REQUIRED"


def _bound_preview(
    path: str = "README.md",
    *,
    target_sha: str = "b" * 64,
    head_sha: str = "a" * 40,
    git_sha: str = "c" * 64,
) -> dict[str, object]:
    return {
        "repository_root": r"C:\Repo",
        "path": path,
        "file_size_bytes": 10,
        "target_sha256": target_sha,
        "head_sha": head_sha,
        "git_executable_path": r"C:\Git\git.exe",
        "git_executable_sha256": git_sha,
    }


def test_git_diff_execution_uses_fixed_argv_and_returns_bounded_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    previews = [_bound_preview(), _bound_preview()]
    monkeypatch.setattr(
        adapter,
        "preview_diff_target",
        lambda _raw: previews.pop(0),
    )
    captured = {}

    diff_bytes = (
        b"diff --git a/README.md b/README.md\n"
        b"--- a/README.md\n"
        b"+++ b/README.md\n"
        b"@@ -1 +1 @@\n"
        b"-old\n"
        b"+new\n"
    )

    def fake_run(git_executable, arguments):
        captured["git"] = git_executable
        captured["arguments"] = list(arguments)
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=diff_bytes,
            stderr=b"secret stderr",
        )

    monkeypatch.setattr(adapter, "_run_git", fake_run)

    evidence = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert captured["arguments"] == [
        "diff",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--unified=3",
        "HEAD",
        "--",
        "README.md",
    ]
    assert evidence["diff_text"] == diff_bytes.decode("utf-8")
    assert evidence["diff_bytes"] == len(diff_bytes)
    assert evidence["diff_lines"] == 6
    assert evidence["raw_stderr_returned"] is False
    assert "secret stderr" not in str(evidence)


def test_git_diff_blocks_target_change_before_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(
        adapter,
        "preview_diff_target",
        lambda _raw: _bound_preview(target_sha="d" * 64),
    )

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("git diff must not run")

    monkeypatch.setattr(adapter, "_run_git", must_not_run)

    evidence = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_DIFF_TARGET_CHANGED_AFTER_PREVIEW"


def test_git_diff_blocks_head_change_before_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(
        adapter,
        "preview_diff_target",
        lambda _raw: _bound_preview(head_sha="d" * 40),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("git diff must not run")
        ),
    )

    evidence = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_DIFF_HEAD_CHANGED_AFTER_PREVIEW"


def test_git_diff_invalidates_state_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    previews = [
        _bound_preview(),
        _bound_preview(target_sha="d" * 64),
    ]
    monkeypatch.setattr(
        adapter,
        "preview_diff_target",
        lambda _raw: previews.pop(0),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, arguments: subprocess.CompletedProcess(
            arguments,
            0,
            stdout=b"diff\n",
            stderr=b"",
        ),
    )

    evidence = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_DIFF_STATE_CHANGED_DURING_READ"


def test_git_diff_enforces_output_and_line_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)

    monkeypatch.setattr(
        adapter,
        "preview_diff_target",
        lambda _raw: _bound_preview(),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, arguments: subprocess.CompletedProcess(
            arguments,
            0,
            stdout=b"x" * (MAX_GIT_DIFF_OUTPUT_BYTES + 1),
            stderr=b"",
        ),
    )
    oversized = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )
    assert oversized["error"] == "GIT_DIFF_OUTPUT_TOO_LARGE"

    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, arguments: subprocess.CompletedProcess(
            arguments,
            0,
            stdout=(b"x\n" * (MAX_GIT_DIFF_LINES + 1)),
            stderr=b"",
        ),
    )
    too_many_lines = adapter.diff_file(
        "README.md",
        expected_path="README.md",
        expected_target_sha256="b" * 64,
        expected_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )
    assert too_many_lines["error"] == "GIT_DIFF_LINE_LIMIT_EXCEEDED"


class _PreviewAdapter:
    @staticmethod
    def preview_diff_target(_raw):
        return _bound_preview()


def test_git_diff_action_preview_binds_file_head_and_git_identity() -> None:
    action = GitDiffFileAction(_PreviewAdapter())
    preview = action.confirmation_preview(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": "README.md"},
        )
    )

    assert preview.allowed is True
    assert preview.execution_guard["_expected_git_diff_path"] == "README.md"
    assert preview.execution_guard["_expected_git_diff_target_sha256"] == "b" * 64
    assert preview.execution_guard["_expected_git_diff_head_sha256"] == "a" * 40
    assert "conteúdo do diff será enviado" in preview.text
    assert "Nenhuma operação de stage" in preview.text
    assert "diff --git" not in preview.text


def test_git_diff_action_risk_escalates_sensitive_names() -> None:
    assert GitDiffFileAction.risk_for(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": "README.md"},
        )
    ) is ActionRisk.CONFIRM
    assert GitDiffFileAction.risk_for(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": ".env"},
        )
    ) is ActionRisk.PRIVILEGED
    assert GitDiffFileAction.risk_for(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": "keys/id_rsa"},
        )
    ) is ActionRisk.PRIVILEGED


def test_git_diff_execute_requires_approved_preview() -> None:
    class _NoRunAdapter:
        def diff_file(self, *args, **kwargs):
            _ = args, kwargs
            raise AssertionError("diff must not run")

    result = GitDiffFileAction(_NoRunAdapter()).execute(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": "README.md"},
        )
    )

    assert result.success is False
    assert result.error_code == "GIT_DIFF_PREVIEW_REQUIRED"


def test_bootstrap_registers_git_diff_file_action() -> None:
    registry = build_action_registry()
    ordinary = ActionRequest(
        action="git_diff_file",
        arguments={"path": "README.md"},
    )
    sensitive = ActionRequest(
        action="git_diff_file",
        arguments={"path": ".env"},
    )

    assert registry.contains("git_diff_file") is True
    assert registry.risk_for(ordinary) is ActionRisk.CONFIRM
    assert registry.risk_for(sensitive) is ActionRisk.PRIVILEGED


class _DiffProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_diff_file",
                    arguments={"path": "README.md"},
                    call_id="git_diff_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Diff recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_diff_gate_does_not_read_diff_before_confirmation() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Diff Git coletado.",
        )

    registry.register(
        GitDiffFileAction.name,
        handler,
        risk=GitDiffFileAction.risk_for,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _DiffProvider(),
        registry,
        catalog,
    ).execute(
        "Mostre o diff de README.md.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_git_diff_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(
            action="git_diff_file",
            arguments={"path": "README.md"},
        )
    )

    assert message == "Inspecionando diff Git de README.md..."
