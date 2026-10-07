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
from theos.core.actions.git_local import GitRemoteIdentitySnapshotAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    FIXED_GIT_REMOTE_FETCH,
    FIXED_GIT_REMOTE_NAME,
    FIXED_GIT_REMOTE_REF,
    FIXED_GIT_REMOTE_URL,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _verifier(repo: Path) -> dict[str, object]:
    return {
        "repository_root": str(repo.resolve()),
        "git_executable_path": r"C:\Git\git.exe",
        "git_executable_sha256": "c" * 64,
        "git_executable_size_bytes": 7,
    }


def test_git_remote_identity_catalog_has_no_model_arguments() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_remote_identity_snapshot"]

    assert len(definitions) == 61
    assert definition.parameters["properties"] == {}
    assert definition.parameters["additionalProperties"] is False
    assert "configuração Git local" in definition.description
    assert "Não há contato de rede" in definition.description

    request = catalog.build_action_request(
        ToolCall(name="git_remote_identity_snapshot", arguments={})
    )
    assert request.arguments == {}

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="git_remote_identity_snapshot",
                arguments={"remote": "evil"},
            )
        )


def test_git_remote_identity_config_reader_uses_fixed_local_config_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    calls = []

    def fake_run(_git, args):
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(FIXED_GIT_REMOTE_URL + "\n").encode(),
            stderr=b"",
        )

    monkeypatch.setattr(adapter, "_run_git", fake_run)

    values, error = adapter._read_local_config_values(
        Path("git.exe"),
        "remote.origin.url",
    )

    assert error is None
    assert values == [FIXED_GIT_REMOTE_URL]
    assert calls == [
        ["config", "--local", "--get-all", "remote.origin.url"]
    ]


def test_git_remote_identity_success_is_exact_and_no_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    def fake_run(_git, args):
        mapping = {
            ("rev-parse", "--show-toplevel"): str(repo).encode(),
            ("rev-parse", "--verify", "HEAD"): b"a" * 40,
            ("branch", "--show-current"): b"main",
        }
        payload = mapping.get(tuple(args))
        if payload is None:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(adapter, "_run_git", fake_run)

    expected = {
        "remote.origin.url": [FIXED_GIT_REMOTE_URL],
        "remote.origin.fetch": [FIXED_GIT_REMOTE_FETCH],
        "branch.main.remote": [FIXED_GIT_REMOTE_NAME],
        "branch.main.merge": [FIXED_GIT_REMOTE_REF],
        "remote.origin.pushurl": [],
        "remote.origin.push": [],
        "remote.pushDefault": [],
        "branch.main.pushRemote": [],
        "remote.origin.receivepack": [],
        "remote.origin.uploadpack": [],
        "core.sshCommand": [],
    }
    monkeypatch.setattr(
        adapter,
        "_read_local_config_values",
        lambda _git, key: (expected[key], None),
    )
    monkeypatch.setattr(
        adapter,
        "_local_url_rewrite_present",
        lambda _git: (False, None),
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert "error" not in evidence
    assert evidence["remote_identity_exact_match"] is True
    assert evidence["remote_name"] == "origin"
    assert evidence["remote_url"] == FIXED_GIT_REMOTE_URL
    assert evidence["branch"] == "main"
    assert evidence["tracking_ref"] == "refs/heads/main"
    assert evidence["network_contact"] is False
    assert evidence["git_remote_authority"] is False
    assert evidence["push_authority"] is False
    assert evidence["remote_config_observed_values_returned"] is False


def test_git_remote_identity_rejects_url_mismatch_without_returning_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    outputs = {
        ("rev-parse", "--show-toplevel"): str(repo).encode(),
        ("rev-parse", "--verify", "HEAD"): b"a" * 40,
        ("branch", "--show-current"): b"main",
    }
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            stdout=outputs[tuple(args)],
            stderr=b"",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_read_local_config_values",
        lambda _git, key: (
            ["https://example.invalid/secret.git"]
            if key == "remote.origin.url"
            else [],
            None,
        ),
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_IDENTITY_URL_MISMATCH"
    assert "https://example.invalid/secret.git" not in repr(evidence)
    assert "remote_url" not in evidence


@pytest.mark.parametrize(
    ("key", "error_code"),
    (
        ("remote.origin.pushurl", "GIT_REMOTE_IDENTITY_PUSHURL_NOT_ALLOWED"),
        ("remote.origin.push", "GIT_REMOTE_IDENTITY_PUSH_REFSPEC_NOT_ALLOWED"),
        ("remote.pushDefault", "GIT_REMOTE_IDENTITY_PUSH_DEFAULT_NOT_ALLOWED"),
        (
            "branch.main.pushRemote",
            "GIT_REMOTE_IDENTITY_BRANCH_PUSH_REMOTE_NOT_ALLOWED",
        ),
    ),
)
def test_git_remote_identity_rejects_local_push_redirection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    error_code: str,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    outputs = {
        ("rev-parse", "--show-toplevel"): str(repo).encode(),
        ("rev-parse", "--verify", "HEAD"): b"a" * 40,
        ("branch", "--show-current"): b"main",
    }
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            stdout=outputs[tuple(args)],
            stderr=b"",
        ),
    )

    exact = {
        "remote.origin.url": [FIXED_GIT_REMOTE_URL],
        "remote.origin.fetch": [FIXED_GIT_REMOTE_FETCH],
        "branch.main.remote": [FIXED_GIT_REMOTE_NAME],
        "branch.main.merge": [FIXED_GIT_REMOTE_REF],
    }

    def read_config(_git, requested_key):
        if requested_key in exact:
            return exact[requested_key], None
        if requested_key == key:
            return ["blocked-value"], None
        return [], None

    monkeypatch.setattr(adapter, "_read_local_config_values", read_config)

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == error_code
    assert "blocked-value" not in repr(evidence)


def test_git_remote_identity_rejects_local_url_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    outputs = {
        ("rev-parse", "--show-toplevel"): str(repo).encode(),
        ("rev-parse", "--verify", "HEAD"): b"a" * 40,
        ("branch", "--show-current"): b"main",
    }
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            stdout=outputs[tuple(args)],
            stderr=b"",
        ),
    )
    exact = {
        "remote.origin.url": [FIXED_GIT_REMOTE_URL],
        "remote.origin.fetch": [FIXED_GIT_REMOTE_FETCH],
        "branch.main.remote": [FIXED_GIT_REMOTE_NAME],
        "branch.main.merge": [FIXED_GIT_REMOTE_REF],
    }
    monkeypatch.setattr(
        adapter,
        "_read_local_config_values",
        lambda _git, key: (exact.get(key, []), None),
    )
    monkeypatch.setattr(
        adapter,
        "_local_url_rewrite_present",
        lambda _git: (True, None),
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_IDENTITY_URL_REWRITE_NOT_ALLOWED"


def test_git_remote_identity_rejects_tracking_ref_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    outputs = {
        ("rev-parse", "--show-toplevel"): str(repo).encode(),
        ("rev-parse", "--verify", "HEAD"): b"a" * 40,
        ("branch", "--show-current"): b"main",
    }
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            stdout=outputs[tuple(args)],
            stderr=b"",
        ),
    )
    exact = {
        "remote.origin.url": [FIXED_GIT_REMOTE_URL],
        "remote.origin.fetch": [FIXED_GIT_REMOTE_FETCH],
        "branch.main.remote": [FIXED_GIT_REMOTE_NAME],
        "branch.main.merge": ["refs/heads/not-main"],
    }
    monkeypatch.setattr(
        adapter,
        "_read_local_config_values",
        lambda _git, key: (exact.get(key, []), None),
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_IDENTITY_TRACKING_REF_MISMATCH"


def test_git_remote_identity_rejects_non_main_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path.resolve()
    adapter = WindowsLocalGitAdapter(repo)
    monkeypatch.setattr(adapter, "preview_git_executable", lambda: _verifier(repo))

    outputs = {
        ("rev-parse", "--show-toplevel"): str(repo).encode(),
        ("rev-parse", "--verify", "HEAD"): b"a" * 40,
        ("branch", "--show-current"): b"feature",
    }
    monkeypatch.setattr(
        adapter,
        "_run_git",
        lambda _git, args: subprocess.CompletedProcess(
            args,
            0,
            stdout=outputs[tuple(args)],
            stderr=b"",
        ),
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_IDENTITY_BRANCH_MISMATCH"


def test_git_remote_identity_blocks_changed_git_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "d" * 64,
        },
    )

    evidence = adapter.remote_identity_snapshot(
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"


class _PreviewAdapter:
    @staticmethod
    def preview_git_executable():
        return {
            "repository_root": r"C:\Repo",
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "c" * 64,
            "git_executable_size_bytes": 7,
        }


def test_git_remote_identity_action_preview_is_confirm_and_static_identity() -> None:
    action = GitRemoteIdentitySnapshotAction(_PreviewAdapter())
    preview = action.confirmation_preview(
        ActionRequest(action="git_remote_identity_snapshot", arguments={})
    )

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert FIXED_GIT_REMOTE_URL in preview.text
    assert "Nenhum contato de rede" in preview.text
    assert "url.*.insteadOf" in preview.text
    assert (
        preview.execution_guard["_expected_git_executable_sha256"]
        == "c" * 64
    )


def test_git_remote_identity_action_registration_and_missing_preview_guard() -> None:
    class _NoRunAdapter:
        def remote_identity_snapshot(self, **kwargs):
            _ = kwargs
            raise AssertionError("remote identity must not run")

    missing = GitRemoteIdentitySnapshotAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_remote_identity_snapshot", arguments={})
    )
    assert missing.success is False
    assert missing.error_code == "GIT_REMOTE_IDENTITY_PREVIEW_REQUIRED"

    registry = build_action_registry()
    request = ActionRequest(action="git_remote_identity_snapshot", arguments={})
    assert registry.contains("git_remote_identity_snapshot") is True
    assert registry.risk_for(request) is ActionRisk.CONFIRM


class _RemoteIdentityProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_remote_identity_snapshot",
                    arguments={},
                    call_id="git_remote_identity_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="Identidade remota recebida.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_remote_identity_gate_and_progress() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="Identidade remota verificada.",
        )

    registry.register(
        GitRemoteIdentitySnapshotAction.name,
        handler,
        risk=GitRemoteIdentitySnapshotAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _RemoteIdentityProvider(),
        registry,
        catalog,
    ).execute(
        "Valide a identidade remota local.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []

    message = ToolLoopExecutor._progress_message(
        ActionRequest(action="git_remote_identity_snapshot", arguments={})
    )
    assert message == "Validando identidade Git remota local..."
