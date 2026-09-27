from __future__ import annotations

from pathlib import Path

from theos.core.actions.file_system import WriteTextFileAction
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import AIContinuation, AIReply, AIToolTurn
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.lyra.execution import ToolLoopExecutor


class WriteProvider:
    provider_id = "fake"

    def __init__(self, path: str) -> None:
        self.path = path
        self.continuations = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        return AIToolTurn(
            calls=(
                ToolCall(
                    name="write_text_file",
                    arguments={
                        "path": self.path,
                        "content": "LYRA M11 live-safe content\n",
                    },
                    call_id="write_1",
                ),
            ),
            continuation=AIContinuation(provider_id="fake", state=1),
            provider_id="fake",
        )

    def continue_after_tools(self, turn, results):
        _ = turn, results
        self.continuations += 1
        return AIReply(text="Arquivo criado.", provider_id="fake")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id="fake")


def _stack(target: Path):
    action = WriteTextFileAction(WindowsFileSystemAdapter())
    registry = ActionRegistry()
    registry.register(
        action.name,
        action.execute,
        risk=action.risk_for,
        confirmation_preview=action.confirmation_preview,
    )
    catalog = build_default_tool_catalog()
    provider = WriteProvider(str(target))
    executor = ToolLoopExecutor(provider, registry, catalog)
    return registry, catalog, provider, executor


def test_write_tool_does_not_mutate_before_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    registry, catalog, provider, executor = _stack(target)

    waiting = executor.execute(
        "Crie o arquivo",
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


def test_write_tool_executes_only_with_local_preview_guard(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    registry, catalog, provider, executor = _stack(target)

    waiting = executor.execute(
        "Crie o arquivo",
        tools=catalog.definitions(),
    )
    pending = waiting.pending_confirmation
    assert pending is not None

    preview = registry.confirmation_preview_for(pending.request)
    assert preview is not None
    assert preview.allowed is True
    pending.request.arguments.update(preview.execution_guard)

    completed = executor.resume(pending, approved=True)

    assert completed.success is True
    assert target.read_text(encoding="utf-8") == "LYRA M11 live-safe content\n"
    assert provider.continuations == 1
