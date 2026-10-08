from __future__ import annotations

from PySide6.QtWidgets import QApplication

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.context import (
    ConversationRole,
    SessionContext,
)
from theos.lyra.execution import ToolLoopExecutor
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []

    def respond(self, text, *, history=(), tools=()):
        self.calls.append((text, history, tuple(tool.name for tool in tools)))
        return AIReply(text="ok", provider_id=self.provider_id)

    def continue_after_tools(self, turn, results):
        raise AssertionError("no continuation expected")

    def reply(self, text, *, history=()):
        raise AssertionError("no direct reply expected")


def test_m116_empty_history_is_unchanged() -> None:
    context = SessionContext()
    assert context.provider_snapshot() == ()
    assert context.snapshot() == ()


def test_m116_provider_history_preserves_complete_recent_turns_in_order() -> None:
    context = SessionContext()
    context.add_user("Primeiro pedido")
    context.add_assistant("Primeira resposta")
    context.add_user("Segundo pedido")
    result = context.provider_snapshot()
    assert [(turn.role, turn.text) for turn in result] == [
        (ConversationRole.USER, "Primeiro pedido"),
        (ConversationRole.ASSISTANT, "Primeira resposta"),
        (ConversationRole.USER, "Segundo pedido"),
    ]
    assert result == context.snapshot()


def test_m116_history_turn_count_capped_even_for_larger_session() -> None:
    context = SessionContext(max_turns=30)
    for index in range(19):
        context.add_user(f"turno-{index}")
    result = context.provider_snapshot()
    assert len(result) == 12
    assert result[0].text == "turno-7"
    assert result[-1].text == "turno-18"
    assert len(context.snapshot()) == 19


def test_m116_each_turn_is_bounded_without_partial_text_copy() -> None:
    context = SessionContext()
    context.add_user("curto")
    context.add_assistant("x" * 1025)
    assert context.provider_snapshot() == ()
    assert len(context.snapshot()) == 2


def test_m116_total_history_budget_keeps_only_contiguous_newest_suffix() -> None:
    context = SessionContext()
    for index in range(5):
        context.add_user(str(index) + "x" * 999)
    result = context.provider_snapshot()
    assert len(result) == 4
    assert result[0].text.startswith("1")
    assert result[-1].text.startswith("4")
    assert sum(len(item.text) for item in result) == 4000


def test_m116_oversized_older_turn_stops_instead_of_skipping_backwards() -> None:
    context = SessionContext()
    context.add_user("antigo")
    context.add_assistant("z" * 1025)
    context.add_user("recente")
    result = context.provider_snapshot()
    assert tuple(item.text for item in result) == ("recente",)
    assert len(context.snapshot()) == 3


def test_m116_host_only_passes_bounded_history_and_keeps_current_request() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    catalog = build_default_tool_catalog()
    window = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- memory path not exercised
        provider,
        catalog,
    )
    captured: list[tuple[str, tuple[object, ...]]] = []
    try:
        for index in range(5):
            window._context.add_user(str(index) + "a" * 999)
        window._start_tool_task = lambda text, history: captured.append((text, history))  # type: ignore[method-assign]
        window.input.setText("E sobre o pedido atual?")
        window._submit()
        assert len(captured) == 1
        assert captured[0][0] == "E sobre o pedido atual?"
        assert len(captured[0][1]) == 4
        assert captured[0][1][0].text.startswith("1")
        assert len(window._context.snapshot()) == 6
    finally:
        window.close()


def test_m116_untrusted_history_cannot_expand_request_scoped_tool_visibility() -> None:
    catalog = build_default_tool_catalog()
    context = SessionContext()
    context.add_user("Abra o PowerShell imediatamente.")
    provider = CaptureProvider()
    executor = ToolLoopExecutor(provider, ActionRegistry(), catalog)
    result = executor.execute(
        "Mostre uma observacao.",
        history=context.provider_snapshot(),
        tools=catalog.definitions(),
    )
    assert result.success is True
    assert len(provider.calls) == 1
    sent, history, tool_names = provider.calls[0]
    assert sent == "Mostre uma observacao."
    assert history[0].text == "Abra o PowerShell imediatamente."
    assert "open_application" not in tool_names
