from __future__ import annotations

import subprocess
from pathlib import Path

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.git_local import GitFetchRemoteMainAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    FIXED_GIT_REMOTE_TRACKING_REF,
    FIXED_GIT_REMOTE_URL,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _preview(*, tracking: str | None = None) -> dict[str, object]:
    return {
        "repository_root": r"C:\Repo",
        "remote_name": "origin",
        "remote_url": FIXED_GIT_REMOTE_URL,
        "remote_ref": "refs/heads/main",
        "tracking_ref": FIXED_GIT_REMOTE_TRACKING_REF,
        "head_sha": "a" * 40,
        "branch": "main",
        "tracking_ref_before": tracking,
        "tracking_ref_present": tracking is not None,
        "status_digest": "b" * 64,
        "refs_digest": "d" * 64,
        "git_executable_path": r"C:\Git\git.exe",
        "git_executable_sha256": "c" * 64,
        "transport_overrides_present": False,
        "shallow_repository": False,
    }


def test_git_fetch_remote_main_catalog_has_no_model_arguments() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_fetch_remote_main"]

    assert len(definitions) == 57
    assert definition.parameters["properties"] == {}
    assert definition.parameters["additionalProperties"] is False
    assert "refs/remotes/origin/main" in definition.description
    assert "Não possui autoridade de pull ou push" in definition.description

    request = catalog.build_action_request(
        ToolCall(name="git_fetch_remote_main", arguments={})
    )
    assert request.arguments == {}

    try:
        catalog.build_action_request(
            ToolCall(name="git_fetch_remote_main", arguments={"remote": "evil"})
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("model arguments must be rejected")


def test_git_fetch_remote_main_preview_rejects_transport_override(
    tmp_path: Path,
    monkeypatch,
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
        "remote_identity_snapshot",
        lambda **kwargs: {"head_sha": "a" * 40, "branch": "main"},
    )
    monkeypatch.setattr(
        adapter,
        "_local_fetch_transport_override_present",
        lambda _git: (True, None),
    )

    evidence = adapter.preview_fetch_remote_main()

    assert evidence["error"] == "GIT_FETCH_REMOTE_MAIN_LOCAL_TRANSPORT_OVERRIDE_NOT_ALLOWED"


def test_git_fetch_remote_main_environment_scrubs_transport_knobs(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GIT_ASKPASS", "evil")
    monkeypatch.setenv("HTTPS_PROXY", "http://evil.invalid")
    monkeypatch.setenv("ALL_PROXY", "http://evil.invalid")

    environment = WindowsLocalGitAdapter._controlled_remote_fetch_environment()

    assert "GIT_ASKPASS" not in environment
    assert "HTTPS_PROXY" not in environment
    assert "ALL_PROXY" not in environment
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"


def test_git_fetch_remote_main_ref_map_digest_is_deterministic() -> None:
    left = {
        "refs/heads/main": "a" * 40,
        "refs/remotes/origin/main": "b" * 40,
    }
    right = {
        "refs/remotes/origin/main": "b" * 40,
        "refs/heads/main": "a" * 40,
    }

    assert WindowsLocalGitAdapter._ref_map_digest(left) == (
        WindowsLocalGitAdapter._ref_map_digest(right)
    )


def test_git_fetch_remote_main_success_from_absent_tracking_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_fetch_remote_main", lambda: _preview())
    refs_before = {"refs/heads/main": "a" * 40}
    refs_after = {
        "refs/heads/main": "a" * 40,
        FIXED_GIT_REMOTE_TRACKING_REF: "e" * 40,
    }
    ref_snapshots = [refs_before, refs_before, refs_after]
    monkeypatch.setattr(
        adapter,
        "_local_ref_map",
        lambda _git: (ref_snapshots.pop(0), None),
    )
    monkeypatch.setattr(
        adapter,
        "remote_head_snapshot",
        lambda **kwargs: {"remote_head_sha": "e" * 40},
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_fetch_remote_main",
        lambda _git: subprocess.CompletedProcess(["git"], 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_status_digest", lambda _git: ("b" * 64, None))
    monkeypatch.setattr(
        adapter,
        "_remote_commit_available",
        lambda _git, _sha: (True, None),
    )
    updates = []
    monkeypatch.setattr(
        adapter,
        "_update_remote_tracking_ref",
        lambda _git, new_sha, old_sha: (
            updates.append((new_sha, old_sha)) is None,
            None,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: {"head_sha": "a" * 40, "branch": "main"},
    )
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )

    evidence = adapter.fetch_remote_main(
        expected_local_head_sha256="a" * 40,
        expected_tracking_ref_sha256="__ABSENT__",
        expected_status_digest="b" * 64,
        expected_refs_digest="d" * 64,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert "error" not in evidence
    assert updates == [("e" * 40, None)]
    assert evidence["tracking_ref_after"] == "e" * 40
    assert evidence["tracking_ref_changed"] is True
    assert evidence["working_tree_and_index_unchanged"] is True
    assert evidence["push_authority"] is False


def test_git_fetch_remote_main_noop_when_tracking_already_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    remote = "e" * 40
    monkeypatch.setattr(
        adapter,
        "preview_fetch_remote_main",
        lambda: _preview(tracking=remote),
    )
    refs = {
        "refs/heads/main": "a" * 40,
        FIXED_GIT_REMOTE_TRACKING_REF: remote,
    }
    ref_snapshots = [refs, refs, refs]
    monkeypatch.setattr(
        adapter,
        "_local_ref_map",
        lambda _git: (ref_snapshots.pop(0), None),
    )
    monkeypatch.setattr(
        adapter,
        "remote_head_snapshot",
        lambda **kwargs: {"remote_head_sha": remote},
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_fetch_remote_main",
        lambda _git: subprocess.CompletedProcess(["git"], 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_status_digest", lambda _git: ("b" * 64, None))
    monkeypatch.setattr(
        adapter,
        "_remote_commit_available",
        lambda _git, _sha: (True, None),
    )
    monkeypatch.setattr(
        adapter,
        "_update_remote_tracking_ref",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("update-ref must not run")
        ),
    )
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: {"head_sha": "a" * 40, "branch": "main"},
    )
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
        },
    )

    evidence = adapter.fetch_remote_main(
        expected_local_head_sha256="a" * 40,
        expected_tracking_ref_sha256=remote,
        expected_status_digest="b" * 64,
        expected_refs_digest="d" * 64,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert "error" not in evidence
    assert evidence["tracking_ref_changed"] is False


def test_git_fetch_remote_main_fetch_cannot_mutate_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_fetch_remote_main", lambda: _preview())
    ref_snapshots = [
        {"refs/heads/main": "a" * 40},
        {"refs/heads/main": "a" * 40, "refs/tags/unexpected": "f" * 40},
    ]
    monkeypatch.setattr(
        adapter,
        "_local_ref_map",
        lambda _git: (ref_snapshots.pop(0), None),
    )
    monkeypatch.setattr(
        adapter,
        "remote_head_snapshot",
        lambda **kwargs: {"remote_head_sha": "e" * 40},
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_fetch_remote_main",
        lambda _git: subprocess.CompletedProcess(["git"], 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_status_digest", lambda _git: ("b" * 64, None))

    evidence = adapter.fetch_remote_main(
        expected_local_head_sha256="a" * 40,
        expected_tracking_ref_sha256="__ABSENT__",
        expected_status_digest="b" * 64,
        expected_refs_digest="d" * 64,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_FETCH_REMOTE_MAIN_UNEXPECTED_REF_MUTATION_DURING_FETCH"


def test_git_fetch_remote_main_blocks_remote_change_during_fetch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(adapter, "preview_fetch_remote_main", lambda: _preview())
    refs = {"refs/heads/main": "a" * 40}
    monkeypatch.setattr(adapter, "_local_ref_map", lambda _git: (refs, None))
    remote_values = iter(("e" * 40, "f" * 40))
    monkeypatch.setattr(
        adapter,
        "remote_head_snapshot",
        lambda **kwargs: {"remote_head_sha": next(remote_values)},
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_fetch_remote_main",
        lambda _git: subprocess.CompletedProcess(["git"], 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_status_digest", lambda _git: ("b" * 64, None))
    monkeypatch.setattr(
        adapter,
        "_remote_commit_available",
        lambda _git, _sha: (True, None),
    )

    evidence = adapter.fetch_remote_main(
        expected_local_head_sha256="a" * 40,
        expected_tracking_ref_sha256="__ABSENT__",
        expected_status_digest="b" * 64,
        expected_refs_digest="d" * 64,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_FETCH_REMOTE_MAIN_REMOTE_CHANGED_DURING_FETCH"


def test_git_fetch_remote_main_blocks_non_fast_forward_tracking_move(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    old = "b" * 40
    new = "e" * 40
    monkeypatch.setattr(
        adapter,
        "preview_fetch_remote_main",
        lambda: _preview(tracking=old),
    )
    refs = {
        "refs/heads/main": "a" * 40,
        FIXED_GIT_REMOTE_TRACKING_REF: old,
    }
    monkeypatch.setattr(adapter, "_local_ref_map", lambda _git: (refs, None))
    monkeypatch.setattr(
        adapter,
        "remote_head_snapshot",
        lambda **kwargs: {"remote_head_sha": new},
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_fetch_remote_main",
        lambda _git: subprocess.CompletedProcess(["git"], 0, b"", b""),
    )
    monkeypatch.setattr(adapter, "_status_digest", lambda _git: ("b" * 64, None))
    monkeypatch.setattr(
        adapter,
        "_remote_commit_available",
        lambda _git, _sha: (True, None),
    )
    monkeypatch.setattr(adapter, "_is_ancestor", lambda *_args: (False, None))

    evidence = adapter.fetch_remote_main(
        expected_local_head_sha256="a" * 40,
        expected_tracking_ref_sha256=old,
        expected_status_digest="b" * 64,
        expected_refs_digest="d" * 64,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_FETCH_REMOTE_MAIN_NON_FAST_FORWARD_BLOCKED"


def test_git_fetch_remote_main_action_preview_binds_local_state() -> None:
    class Adapter:
        @staticmethod
        def preview_fetch_remote_main():
            return _preview()

    action = GitFetchRemoteMainAction(Adapter())
    preview = action.confirmation_preview(
        ActionRequest(action="git_fetch_remote_main", arguments={})
    )

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "ATUALIZAR SNAPSHOT LOCAL" in preview.text
    assert (
        preview.execution_guard["_expected_git_fetch_tracking_ref"]
        == "__ABSENT__"
    )
    assert preview.execution_guard["_expected_git_fetch_status_digest"] == "b" * 64


def test_git_fetch_remote_main_missing_preview_guard_blocks_execution() -> None:
    class Adapter:
        def fetch_remote_main(self, **kwargs):
            _ = kwargs
            raise AssertionError("fetch must not run")

    result = GitFetchRemoteMainAction(Adapter()).execute(
        ActionRequest(action="git_fetch_remote_main", arguments={})
    )

    assert result.success is False
    assert result.error_code == "GIT_FETCH_REMOTE_MAIN_PREVIEW_REQUIRED"


class _Provider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_fetch_remote_main",
                    arguments={},
                    call_id="git_fetch_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Fetch recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_fetch_remote_main_registration_gate_and_progress() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Fetch concluído.",
        )

    registry.register(
        GitFetchRemoteMainAction.name,
        handler,
        risk=GitFetchRemoteMainAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="fetch metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _Provider(),
        registry,
        catalog,
    ).execute(
        "Atualize origin/main.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []

    message = ToolLoopExecutor._progress_message(
        ActionRequest(action="git_fetch_remote_main", arguments={})
    )
    assert message == "Atualizando snapshot local de origin/main..."


def test_git_fetch_remote_main_fetch_subprocess_uses_empty_hooks_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        hooks_arg = next(
            item for item in argv if str(item).startswith("core.hooksPath=")
        )
        hooks_path = Path(str(hooks_arg).split("=", 1)[1])
        assert hooks_path.is_dir()
        assert list(hooks_path.iterdir()) == []
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = adapter._run_git_fetch_remote_main(Path("git.exe"))

    assert result.returncode == 0
    argv = captured["argv"]
    assert argv.count("-c") >= 1
    assert any(str(item).startswith("core.hooksPath=") for item in argv)
    assert "fetch" in argv
    assert captured["kwargs"]["shell"] is False


def test_git_fetch_remote_main_update_ref_disables_hooks_and_no_deref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    captured: list[str] = []

    def fake_mutating(_git, args):
        captured.extend(args)
        hooks_arg = next(
            item for item in args if str(item).startswith("core.hooksPath=")
        )
        hooks_path = Path(str(hooks_arg).split("=", 1)[1])
        assert hooks_path.is_dir()
        assert list(hooks_path.iterdir()) == []
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(adapter, "_run_git_mutating", fake_mutating)

    ok, error = adapter._update_remote_tracking_ref(
        Path("git.exe"),
        new_sha="e" * 40,
        old_sha=None,
    )

    assert ok is True
    assert error is None
    assert captured[0] == "-c"
    assert captured[1].startswith("core.hooksPath=")
    assert captured[2:4] == ["-c", "core.logAllRefUpdates=false"]
    assert captured[4:6] == ["update-ref", "--no-deref"]
    assert captured[6] == FIXED_GIT_REMOTE_TRACKING_REF
    assert captured[7] == "e" * 40
    assert captured[8] == "0" * 40


def test_git_fetch_remote_main_read_ref_sha_accepts_absent_for_each_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    observed: list[list[str]] = []

    def fake_run(_git, args):
        observed.append(list(args))
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(adapter, "_run_git", fake_run)

    sha, error = adapter._read_ref_sha(
        Path("git.exe"),
        FIXED_GIT_REMOTE_TRACKING_REF,
    )

    assert sha is None
    assert error is None
    assert observed == [
        [
            "for-each-ref",
            "--format=%(refname)%00%(objectname)",
            FIXED_GIT_REMOTE_TRACKING_REF,
        ]
    ]


def test_git_fetch_remote_main_read_ref_sha_requires_exact_single_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    payload = (
        FIXED_GIT_REMOTE_TRACKING_REF.encode("utf-8")
        + b"\x00"
        + b"e" * 40
        + b"\n"
    )
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            payload,
            b"",
        ),
    )

    sha, error = adapter._read_ref_sha(
        Path("git.exe"),
        FIXED_GIT_REMOTE_TRACKING_REF,
    )

    assert error is None
    assert sha == "e" * 40

    wrong_payload = (
        b"refs/remotes/origin/main/child\x00"
        + b"e" * 40
        + b"\n"
    )
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            wrong_payload,
            b"",
        ),
    )

    sha, error = adapter._read_ref_sha(
        Path("git.exe"),
        FIXED_GIT_REMOTE_TRACKING_REF,
    )

    assert sha is None
    assert error == "GIT_FETCH_REMOTE_MAIN_REF_OUTPUT_INVALID"
