from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.git_local import GitStatusSnapshotAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    MAX_GIT_STATUS_ENTRIES,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def test_git_preview_hashes_concrete_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_exe = tmp_path / "git.exe"
    git_exe.write_bytes(b"M83_GIT_EXECUTABLE")
    monkeypatch.setattr(
        WindowsLocalGitAdapter,
        "_git_executable",
        staticmethod(lambda: git_exe),
    )

    evidence = WindowsLocalGitAdapter(repo).preview_git_executable()

    assert evidence["git_executable_path"] == str(git_exe.resolve())
    assert evidence["git_executable_size_bytes"] == len(b"M83_GIT_EXECUTABLE")
    assert evidence["git_executable_sha256"] == hashlib.sha256(
        b"M83_GIT_EXECUTABLE"
    ).hexdigest()
    assert evidence["git_executable_content_returned"] is False


def test_git_run_uses_fixed_root_no_shell_and_scrubbed_git_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_exe = tmp_path / "git.exe"
    git_exe.write_bytes(b"x")
    captured = {}

    monkeypatch.setenv("GIT_DIR", r"C:\evil")
    monkeypatch.setenv("GIT_WORK_TREE", r"C:\evil-worktree")
    monkeypatch.setenv("GIT_INDEX_FILE", r"C:\evil-index")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "theos.integrations.windows.git_local.subprocess.run",
        fake_run,
    )

    adapter = WindowsLocalGitAdapter(repo)
    adapter._run_git(git_exe, ["rev-parse", "--verify", "HEAD"])

    assert captured["command"] == [
        str(git_exe),
        "-C",
        str(repo.resolve()),
        "rev-parse",
        "--verify",
        "HEAD",
    ]
    assert captured["kwargs"]["cwd"] == repo.resolve()
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["check"] is False
    environment = captured["kwargs"]["env"]
    assert "GIT_DIR" not in environment
    assert "GIT_WORK_TREE" not in environment
    assert "GIT_INDEX_FILE" not in environment
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"


def _snapshot_adapter(
    tmp_path: Path,
    monkeypatch,
    status_payload: bytes,
) -> tuple[WindowsLocalGitAdapter, Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_exe = tmp_path / "git.exe"
    git_exe.write_bytes(b"M83_GIT")
    git_hash = hashlib.sha256(b"M83_GIT").hexdigest()
    monkeypatch.setattr(
        WindowsLocalGitAdapter,
        "_git_executable",
        staticmethod(lambda: git_exe),
    )

    outputs = [
        subprocess.CompletedProcess(
            [],
            0,
            stdout=str(repo.resolve()).encode("utf-8"),
            stderr=b"",
        ),
        subprocess.CompletedProcess(
            [],
            0,
            stdout=b"a" * 40,
            stderr=b"",
        ),
        subprocess.CompletedProcess(
            [],
            0,
            stdout=b"main",
            stderr=b"",
        ),
        subprocess.CompletedProcess(
            [],
            0,
            stdout=status_payload,
            stderr=b"",
        ),
    ]

    def fake_run(_git, _args):
        return outputs.pop(0)

    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "_run_git", fake_run)
    return adapter, git_exe, git_hash


def test_git_snapshot_parses_bounded_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status = (
        b" M README.md\0"
        b"?? new.txt\0"
        b"R  renamed.py\0original.py\0"
    )
    adapter, git_exe, git_hash = _snapshot_adapter(
        tmp_path,
        monkeypatch,
        status,
    )

    evidence = adapter.snapshot(
        expected_git_executable_path=str(git_exe.resolve()),
        expected_git_executable_sha256=git_hash,
    )

    assert evidence["branch"] == "main"
    assert evidence["head_sha"] == "a" * 40
    assert evidence["clean"] is False
    assert evidence["observed_changes"] == 3
    assert evidence["returned_changes"] == 3
    assert evidence["entries"][0] == {
        "index_status": " ",
        "worktree_status": "M",
        "path": "README.md",
    }
    assert evidence["entries"][2]["path"] == "renamed.py"
    assert evidence["entries"][2]["original_path"] == "original.py"
    assert evidence["git_executable_unchanged"] is True


def test_git_snapshot_caps_returned_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status = b"".join(
        f"?? file-{index}.txt".encode() + b"\0"
        for index in range(MAX_GIT_STATUS_ENTRIES + 6)
    )
    adapter, git_exe, git_hash = _snapshot_adapter(
        tmp_path,
        monkeypatch,
        status,
    )

    evidence = adapter.snapshot(
        expected_git_executable_path=str(git_exe.resolve()),
        expected_git_executable_sha256=git_hash,
    )

    assert evidence["observed_changes"] == MAX_GIT_STATUS_ENTRIES + 6
    assert evidence["returned_changes"] == MAX_GIT_STATUS_ENTRIES
    assert len(evidence["entries"]) == MAX_GIT_STATUS_ENTRIES
    assert evidence["entries_truncated"] is True


def test_git_snapshot_blocks_changed_executable_before_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "repository_root": str(repo.resolve()),
            "git_executable_path": str(tmp_path / "git.exe"),
            "git_executable_sha256": "b" * 64,
            "git_executable_size_bytes": 1,
        },
    )

    def must_not_run(*args, **kwargs):
        _ = args, kwargs
        raise AssertionError("git command must not run")

    monkeypatch.setattr(adapter, "_run_git", must_not_run)

    evidence = adapter.snapshot(
        expected_git_executable_path=str(tmp_path / "git.exe"),
        expected_git_executable_sha256="a" * 64,
    )

    assert evidence["error"] == "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"


def test_git_snapshot_invalidates_if_executable_changes_during_collection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = WindowsLocalGitAdapter(repo)
    verifier_calls = 0

    def fake_preview():
        nonlocal verifier_calls
        verifier_calls += 1
        return {
            "repository_root": str(repo.resolve()),
            "git_executable_path": str(tmp_path / "git.exe"),
            "git_executable_sha256": (
                "a" * 64 if verifier_calls == 1 else "b" * 64
            ),
            "git_executable_size_bytes": 1,
        }

    monkeypatch.setattr(adapter, "preview_git_executable", fake_preview)
    outputs = [
        subprocess.CompletedProcess(
            [], 0, stdout=str(repo.resolve()).encode(), stderr=b""
        ),
        subprocess.CompletedProcess([], 0, stdout=b"a" * 40, stderr=b""),
        subprocess.CompletedProcess([], 0, stdout=b"main", stderr=b""),
        subprocess.CompletedProcess([], 0, stdout=b"", stderr=b""),
    ]
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, _args: outputs.pop(0),
    )

    evidence = adapter.snapshot(
        expected_git_executable_path=str(tmp_path / "git.exe"),
        expected_git_executable_sha256="a" * 64,
    )

    assert evidence["error"] == "GIT_EXECUTABLE_CHANGED_DURING_STATUS"
    assert evidence["git_executable_unchanged"] is False


class _PreviewAdapter:
    repository_root = Path(r"C:\Projetos\TheOS\The-OS")

    @staticmethod
    def preview_git_executable():
        return {
            "repository_root": r"C:\Projetos\TheOS\The-OS",
            "git_executable_path": r"C:\Program Files\Git\cmd\git.exe",
            "git_executable_sha256": "a" * 64,
            "git_executable_size_bytes": 123,
        }


def test_git_action_preview_binds_identity_and_disclosure_boundary() -> None:
    preview = GitStatusSnapshotAction(_PreviewAdapter()).confirmation_preview(
        ActionRequest(action="git_status_snapshot", arguments={})
    )

    assert preview.allowed is True
    assert preview.execution_guard == {
        "_expected_git_executable_path": r"C:\Program Files\Git\cmd\git.exe",
        "_expected_git_executable_sha256": "a" * 64,
    }
    assert "Repositório fixo" in preview.text
    assert "até 64 caminhos alterados" in preview.text
    assert "Conteúdo de diff" in preview.text
    assert "modelo não escolhe repositório" in preview.text


def test_git_action_execute_requires_approved_preview() -> None:
    class _NoRunAdapter:
        def snapshot(self, **kwargs):
            _ = kwargs
            raise AssertionError("snapshot must not run")

    result = GitStatusSnapshotAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_status_snapshot", arguments={})
    )

    assert result.success is False
    assert result.error_code == "GIT_STATUS_PREVIEW_REQUIRED"


def test_git_catalog_registers_no_argument_confirmed_tool() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_status_snapshot"]

    assert len(definitions) == 61
    assert definition.parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    request = catalog.build_action_request(
        ToolCall(
            name="git_status_snapshot",
            arguments={},
        )
    )
    assert request.arguments == {}


def test_bootstrap_registers_git_status_snapshot_action() -> None:
    registry = build_action_registry()
    request = ActionRequest(action="git_status_snapshot", arguments={})

    assert registry.contains("git_status_snapshot") is True
    assert registry.risk_for(request) is ActionRisk.CONFIRM


class _GitStatusProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_status_snapshot",
                    arguments={},
                    call_id="git_status_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Status recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_status_gate_does_not_collect_before_confirmation() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Status Git coletado.",
        )

    registry.register(
        GitStatusSnapshotAction.name,
        handler,
        risk=GitStatusSnapshotAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="git status",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _GitStatusProvider(),
        registry,
        catalog,
    ).execute(
        "Mostre o status Git local.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []


def test_git_status_progress_message_is_specific() -> None:
    message = ToolLoopExecutor._progress_message(
        ActionRequest(action="git_status_snapshot", arguments={})
    )

    assert message == "Inspecionando status Git local..."
