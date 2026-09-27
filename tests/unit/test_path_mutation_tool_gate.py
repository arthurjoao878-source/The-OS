from __future__ import annotations

from pathlib import Path

from theos.core.actions.file_system import CreateDirectoryAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.lyra.execution import ToolLoopExecutor


class DirectoryProvider:
    provider_id = "fake"

    def __init__(self, path: str) -> None:
        self.path = path
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="create_directory",
                    arguments={"path": self.path},
                    call_id="mkdir_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(text="Pasta criada.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def test_create_directory_tool_does_not_mutate_before_confirmation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "new-folder"
    action = CreateDirectoryAction(WindowsFileSystemAdapter())
    registry = ActionRegistry()
    registry.register(
        action.name,
        action.execute,
        risk=action.risk_for,
        confirmation_preview=action.confirmation_preview,
    )
    catalog = build_default_tool_catalog()
    provider = DirectoryProvider(str(target))
    executor = ToolLoopExecutor(provider, registry, catalog)

    waiting = executor.execute(
        "Crie a pasta",
        tools=catalog.definitions(),
    )

    assert waiting.awaiting_confirmation is True
    assert target.exists() is False
    assert provider.continuations == 0

    pending = waiting.pending_confirmation
    assert pending is not None
    preview = registry.confirmation_preview_for(pending.request)
    assert preview is not None
    assert preview.allowed is True
    assert target.exists() is False

    cancelled = executor.resume(pending, approved=False)

    assert cancelled.success is False
    assert target.exists() is False
    assert provider.continuations == 0
