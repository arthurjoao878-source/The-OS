from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.context import SessionContext
from theos.lyra.personality import PersonalityTone
from theos.shell.assistant.draft_recall import recallable_user_drafts
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="ok", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("no continuation expected")

    def reply(self, text, *, history=()):
        raise AssertionError("no direct reply expected")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory_marker = object()
    window = MainWindow(
        ActionRegistry(),
        memory_marker,  # type: ignore[arg-type] -- no memory route in these tests
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m120_controls_are_explicit_and_do_not_send(host) -> None:
    window, provider, _ = host
    assert window.draft_previous.objectName() == "lyra_draft_previous"
    assert window.draft_next.objectName() == "lyra_draft_next"
    window.draft_previous.click()
    window.draft_next.click()
    assert window.input.text() == ""
    assert provider.calls == 0


def test_m120_previous_walks_user_submissions_newest_first(host) -> None:
    window, _, _ = host
    window._context.add_user("Primeiro pedido")
    window._context.add_assistant("Resposta da LYRA")
    window._context.add_user("Segundo pedido")
    window.input.setText("Rascunho original")
    window.draft_previous.click()
    assert window.input.text() == "Segundo pedido"
    window.draft_previous.click()
    assert window.input.text() == "Primeiro pedido"
    window.draft_previous.click()
    assert window.input.text() == "Primeiro pedido"


def test_m120_next_restores_unsent_original_draft(host) -> None:
    window, _, _ = host
    window._context.add_user("Anterior")
    window.input.setText("Texto ainda não enviado")
    window.draft_previous.click()
    assert window.input.text() == "Anterior"
    window.draft_next.click()
    assert window.input.text() == "Texto ainda não enviado"
    window.draft_next.click()
    assert window.input.text() == "Texto ainda não enviado"


def test_m120_only_user_turns_are_eligible_and_complete() -> None:
    session = SessionContext(max_turns=30)
    session.add_user("Pedido válido")
    session.add_assistant("Não reutilizar resposta")
    session.add_user("Z" * 1025)
    session.add_user("Outro pedido")
    assert recallable_user_drafts(session) == ("Pedido válido", "Outro pedido")
    assert len(session.snapshot()) == 4


def test_m120_max_eight_recalled_items_without_new_persistence() -> None:
    session = SessionContext(max_turns=30)
    for index in range(15):
        session.add_user(f"Pedido {index}")
    selected = recallable_user_drafts(session)
    assert len(selected) == 8
    assert selected[0] == "Pedido 7"
    assert selected[-1] == "Pedido 14"
    assert len(session.snapshot()) == 15


def test_m120_oversized_and_multiline_turns_are_not_recalled(host) -> None:
    window, _, _ = host
    window._context.add_user("Z" * 1025)
    window._context.add_user("Linha um\nLinha dois")
    window.input.setText("Meu texto")
    window.draft_previous.click()
    assert window.input.text() == "Meu texto"


def test_m120_manual_text_edit_invalidates_navigation(host) -> None:
    window, _, _ = host
    window._context.add_user("Pedido antigo")
    window.input.setText("Rascunho")
    window.draft_previous.click()
    assert window.input.text() == "Pedido antigo"
    window.input.setText("Pedido alterado")
    window.input.textEdited.emit("Pedido alterado")
    window.draft_next.click()
    assert window.input.text() == "Pedido alterado"
    window.draft_previous.click()
    assert window.input.text() == "Pedido antigo"
    window.draft_next.click()
    assert window.input.text() == "Pedido alterado"


def test_m120_recall_is_passive_without_context_changes(host) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Instrução anterior")
    before_session = window._context.snapshot()
    before_perception = window._perception.snapshot()
    before_personality = window._personality.snapshot()
    window.draft_previous.click()
    window.draft_next.click()
    assert window._context.snapshot() == before_session
    assert window._perception.snapshot() == before_perception
    assert window._personality.snapshot() == before_personality
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m120_explicit_submit_of_recalled_text_uses_normal_path(host) -> None:
    window, provider, _ = host
    window._context.add_user("Qual a próxima etapa?")
    window.draft_previous.click()
    captured: list[tuple[str, tuple[object, ...]]] = []
    window._start_tool_task = (  # type: ignore[method-assign]
        lambda text, history: captured.append((text, history))
    )
    assert provider.calls == 0
    window.send.click()
    assert len(captured) == 1
    assert captured[0][0] == "Qual a próxima etapa?"
    assert captured[0][1][0].text == "Qual a próxima etapa?"
    assert window.input.text() == ""
    window.draft_next.click()
    assert window.input.text() == ""


def test_m120_busy_disables_controls_and_handlers_fail_closed(host) -> None:
    window, _, _ = host
    window._context.add_user("Não reutilizar enquanto ocupado")
    window.input.setText("Rascunho")
    window._set_busy(True)
    try:
        assert not window.draft_previous.isEnabled()
        assert not window.draft_next.isEnabled()
        window._browse_draft_history(older=True)
        assert window.input.text() == "Rascunho"
    finally:
        window._set_busy(False)
    assert window.draft_previous.isEnabled()


def test_m120_reset_clears_navigation_and_preserves_personality(
    host, monkeypatch
) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Pedido anterior")
    window.personality_tone.setCurrentIndex(
        window.personality_tone.findData(PersonalityTone.WARM.value)
    )
    style = window._personality.snapshot()
    window.input.setText("Rascunho")
    window.draft_previous.click()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window._context.snapshot() == ()
    assert window.input.text() == ""
    window.draft_next.click()
    assert window.input.text() == ""
    assert window._personality.snapshot() == style
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m120_other_host_draft_navigation_is_isolated(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory route
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window._context.add_user("Janela principal")
        other._context.add_user("Janela independente")
        window.draft_previous.click()
        assert window.input.text() == "Janela principal"
        assert other.input.text() == ""
        other.draft_previous.click()
        assert other.input.text() == "Janela independente"
    finally:
        other.close()
