from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.git_local import GitRemoteHeadSnapshotAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.git_local import (
    FIXED_GIT_REMOTE_REF,
    FIXED_GIT_REMOTE_URL,
    WindowsLocalGitAdapter,
)
from theos.lyra.execution import ToolLoopExecutor


def _local_identity(
    *,
    head: str = "a" * 40,
) -> dict[str, object]:
    return {
        "repository_root": r"C:\Repo",
        "head_sha": head,
        "branch": "main",
        "remote_name": "origin",
        "remote_url": FIXED_GIT_REMOTE_URL,
        "tracking_ref": FIXED_GIT_REMOTE_REF,
        "remote_identity_exact_match": True,
    }


def _verifier() -> dict[str, object]:
    return {
        "repository_root": r"C:\Repo",
        "git_executable_path": r"C:\Git\git.exe",
        "git_executable_sha256": "c" * 64,
        "git_executable_size_bytes": 7,
    }


def test_git_remote_head_catalog_has_no_model_arguments() -> None:
    catalog = build_default_tool_catalog()
    definitions = {item.name: item for item in catalog.definitions()}
    definition = definitions["git_remote_head_snapshot"]

    assert len(definitions) == 55
    assert definition.parameters["properties"] == {}
    assert definition.parameters["additionalProperties"] is False
    assert "ls-remote" in definition.description
    assert "Não há fetch" in definition.description

    request = catalog.build_action_request(
        ToolCall(name="git_remote_head_snapshot", arguments={})
    )
    assert request.arguments == {}

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="git_remote_head_snapshot",
                arguments={"ref": "refs/heads/other"},
            )
        )


def test_git_remote_head_environment_scrubs_git_and_proxy_knobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_ASKPASS", "evil")
    monkeypatch.setenv("HTTPS_PROXY", "http://evil.invalid")
    monkeypatch.setenv("HTTP_PROXY", "http://evil.invalid")
    monkeypatch.setenv("ALL_PROXY", "http://evil.invalid")
    monkeypatch.setenv("CURL_CA_BUNDLE", "evil-ca")
    monkeypatch.setenv("SSL_CERT_FILE", "evil-cert")

    environment = WindowsLocalGitAdapter._controlled_remote_read_environment()

    assert "GIT_ASKPASS" not in environment
    assert "HTTPS_PROXY" not in environment
    assert "HTTP_PROXY" not in environment
    assert "ALL_PROXY" not in environment
    assert "CURL_CA_BUNDLE" not in environment
    assert "SSL_CERT_FILE" not in environment
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"


def test_git_remote_head_parser_accepts_only_exact_main_ref() -> None:
    payload = (
        b"a" * 40
        + b"\trefs/heads/main\n"
    )

    sha, error = WindowsLocalGitAdapter._parse_remote_head_output(payload)

    assert error is None
    assert sha == "a" * 40


def test_git_remote_head_parser_rejects_multiple_or_other_refs() -> None:
    other = b"a" * 40 + b"\trefs/heads/other\n"
    sha, error = WindowsLocalGitAdapter._parse_remote_head_output(other)
    assert sha is None
    assert error == "GIT_REMOTE_HEAD_OUTPUT_INVALID"

    multiple = (
        b"a" * 40
        + b"\trefs/heads/main\n"
        + b"b" * 40
        + b"\trefs/heads/main\n"
    )
    sha, error = WindowsLocalGitAdapter._parse_remote_head_output(multiple)
    assert sha is None
    assert error == "GIT_REMOTE_HEAD_OUTPUT_INVALID"


def test_git_remote_head_success_revalidates_local_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    identities = [_local_identity(), _local_identity()]

    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: identities.pop(0),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_remote_head",
        lambda _git: subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=b"a" * 40 + b"\trefs/heads/main\n",
            stderr=b"",
        ),
    )
    monkeypatch.setattr(adapter, "preview_git_executable", _verifier)

    evidence = adapter.remote_head_snapshot(
        expected_local_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert "error" not in evidence
    assert evidence["remote_head_sha"] == "a" * 40
    assert evidence["remote_matches_local_head"] is True
    assert evidence["local_identity_revalidated_after_network"] is True
    assert evidence["network_contact"] is True
    assert evidence["fetch_authority"] is False
    assert evidence["push_authority"] is False
    assert evidence["git_mutation_authority"] is False


def test_git_remote_head_changed_local_head_blocks_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: _local_identity(head="d" * 40),
    )

    def fail_network(_git):
        raise AssertionError("network must not run")

    monkeypatch.setattr(adapter, "_run_git_remote_head", fail_network)

    evidence = adapter.remote_head_snapshot(
        expected_local_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_HEAD_LOCAL_HEAD_CHANGED_AFTER_PREVIEW"


def test_git_remote_head_network_failure_does_not_return_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: _local_identity(),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_remote_head",
        lambda _git: subprocess.CompletedProcess(
            ["git"],
            2,
            stdout=b"",
            stderr=b"secret transport detail",
        ),
    )

    evidence = adapter.remote_head_snapshot(
        expected_local_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_HEAD_FAILED"
    assert "secret transport detail" not in repr(evidence)
    assert evidence["raw_stderr_returned"] is False


def test_git_remote_head_invalid_output_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: _local_identity(),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_remote_head",
        lambda _git: subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=b"unexpected\n",
            stderr=b"",
        ),
    )

    evidence = adapter.remote_head_snapshot(
        expected_local_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_REMOTE_HEAD_OUTPUT_INVALID"


def test_git_remote_head_git_identity_change_invalidates_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = WindowsLocalGitAdapter(tmp_path)
    identities = [_local_identity(), _local_identity()]
    monkeypatch.setattr(
        adapter,
        "remote_identity_snapshot",
        lambda **kwargs: identities.pop(0),
    )
    monkeypatch.setattr(
        adapter,
        "_run_git_remote_head",
        lambda _git: subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=b"a" * 40 + b"\trefs/heads/main\n",
            stderr=b"",
        ),
    )
    monkeypatch.setattr(
        adapter,
        "preview_git_executable",
        lambda: {
            "git_executable_path": r"C:\Git\git.exe",
            "git_executable_sha256": "d" * 64,
        },
    )

    evidence = adapter.remote_head_snapshot(
        expected_local_head_sha256="a" * 40,
        expected_git_executable_path=r"C:\Git\git.exe",
        expected_git_executable_sha256="c" * 64,
    )

    assert evidence["error"] == "GIT_EXECUTABLE_CHANGED_DURING_REMOTE_HEAD_READ"


class _PreviewAdapter:
    @staticmethod
    def preview_git_executable():
        return _verifier()

    @staticmethod
    def remote_identity_snapshot(**kwargs):
        _ = kwargs
        return _local_identity()


def test_git_remote_head_action_preview_binds_local_head_and_network_scope() -> None:
    action = GitRemoteHeadSnapshotAction(_PreviewAdapter())
    preview = action.confirmation_preview(
        ActionRequest(action="git_remote_head_snapshot", arguments={})
    )

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert FIXED_GIT_REMOTE_URL in preview.text
    assert "ls-remote --exit-code --heads" in preview.text
    assert "Nenhum fetch" in preview.text
    assert (
        preview.execution_guard["_expected_git_remote_head_local_head"]
        == "a" * 40
    )


def test_git_remote_head_action_missing_preview_guard_blocks_execution() -> None:
    class _NoRunAdapter:
        def remote_head_snapshot(self, **kwargs):
            _ = kwargs
            raise AssertionError("remote head must not run")

    result = GitRemoteHeadSnapshotAction(_NoRunAdapter()).execute(
        ActionRequest(action="git_remote_head_snapshot", arguments={})
    )

    assert result.success is False
    assert result.error_code == "GIT_REMOTE_HEAD_PREVIEW_REQUIRED"


class _RemoteHeadProvider:
    provider_id = "fake"

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="git_remote_head_snapshot",
                    arguments={},
                    call_id="git_remote_head_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        return AIReply(text="HEAD remoto recebido.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_git_remote_head_registration_gate_and_progress() -> None:
    executed = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        executed.append(request)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="HEAD remoto verificado.",
        )

    registry.register(
        GitRemoteHeadSnapshotAction.name,
        handler,
        risk=GitRemoteHeadSnapshotAction.risk,
        confirmation_preview=lambda request: ConfirmationPreview(
            allowed=True,
            text="network metadata only",
        ),
    )
    catalog = build_default_tool_catalog()
    result = ToolLoopExecutor(
        _RemoteHeadProvider(),
        registry,
        catalog,
    ).execute(
        "Leia o HEAD remoto.",
        tools=catalog.definitions(),
    )

    assert result.awaiting_confirmation is True
    assert executed == []

    message = ToolLoopExecutor._progress_message(
        ActionRequest(action="git_remote_head_snapshot", arguments={})
    )
    assert message == "Lendo HEAD remoto Git autorizado..."
