from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
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


def _long_chat(window):
    window.resize(460, 320)
    window.show()
    for i in range(85):
        window._lyra(f"Mensagem visivel {i} com conteudo de leitura.")
    QApplication.instance().processEvents()
    scrollbar = window.chat.verticalScrollBar()
    assert scrollbar.maximum() > scrollbar.minimum()
    return scrollbar


def test_m124_controls_exist_and_transcript_stays_read_only(host) -> None:
    window, provider, _ = host
    assert window.chat_jump_start.objectName() == "lyra_chat_jump_start"
    assert window.chat_jump_end.objectName() == "lyra_chat_jump_end"
    assert window.chat.isReadOnly()
    assert window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m124_start_then_end_moves_real_qt_scrollbar(host) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    window.chat_jump_start.click()
    assert scrollbar.value() == scrollbar.minimum()
    window.chat_jump_end.click()
    assert scrollbar.value() == scrollbar.maximum()


def test_m124_middle_to_edges_and_repeated_clicks_are_idempotent(host) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    scrollbar.setValue(scrollbar.maximum() // 2)
    window.chat_jump_start.click()
    window.chat_jump_start.click()
    assert scrollbar.value() == scrollbar.minimum()
    window.chat_jump_end.click()
    window.chat_jump_end.click()
    assert scrollbar.value() == scrollbar.maximum()


def test_m124_navigation_does_not_modify_transcript_or_find_query(host) -> None:
    window, provider, _ = host
    scrollbar = _long_chat(window)
    window.transcript_find.setText("Mensagem visivel 45")
    window.transcript_find_next.click()
    query = window.transcript_find.text()
    before = window.chat.toPlainText()
    window.chat_jump_start.click()
    window.chat_jump_end.click()
    assert window.chat.toPlainText() == before
    assert window.transcript_find.text() == query
    assert scrollbar.value() == scrollbar.maximum()
    assert provider.calls == 0


def test_m124_follow_off_remains_off_and_append_does_not_follow(host) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    window.chat_follow.setChecked(False)
    window.chat_jump_end.click()
    old_position = scrollbar.value()
    window._lyra("Texto novo nao deve reativar o acompanhamento")
    QApplication.instance().processEvents()
    assert not window.chat_follow.isChecked()
    assert scrollbar.maximum() > old_position
    assert scrollbar.value() == old_position


def test_m124_follow_on_remains_on_and_new_message_autoscrolls(host) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    window.chat_jump_start.click()
    assert window.chat_follow.isChecked()
    window._lyra("Nova mensagem faz acompanhar")
    QApplication.instance().processEvents()
    assert scrollbar.value() == scrollbar.maximum()


def test_m124_buttons_remain_available_when_busy(host) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    window._set_busy(True)
    try:
        assert not window.input.isEnabled()
        assert window.chat_jump_start.isEnabled()
        assert window.chat_jump_end.isEnabled()
        window.chat_jump_start.click()
        assert scrollbar.value() == scrollbar.minimum()
        window.chat_jump_end.click()
        assert scrollbar.value() == scrollbar.maximum()
    finally:
        window._set_busy(False)


def test_m124_navigation_does_not_touch_context_perception_personality_or_memory(host) -> None:
    window, provider, memory_marker = host
    _long_chat(window)
    window._context.add_user("Sessao privada")
    session_before = window._context.snapshot()
    perception_before = window._perception.snapshot()
    personality_before = window._personality.snapshot()
    window.chat_jump_start.click()
    window.chat_jump_end.click()
    assert window._context.snapshot() == session_before
    assert window._perception.snapshot() == perception_before
    assert window._personality.snapshot() == personality_before
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m124_navigation_does_not_change_unsent_draft(host) -> None:
    window, _, _ = host
    _long_chat(window)
    window.input.setText("Rascunho preservado")
    before_counter = window.composer_length_status.text()
    window.chat_jump_start.click()
    window.chat_jump_end.click()
    assert window.input.text() == "Rascunho preservado"
    assert window.composer_length_status.text() == before_counter
    assert window._draft_recall_index is None


def test_m124_denied_new_conversation_does_not_disable_navigation(host, monkeypatch) -> None:
    window, _, _ = host
    scrollbar = _long_chat(window)
    before = window.chat.toPlainText()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    window.chat_jump_start.click()
    assert scrollbar.value() == scrollbar.minimum()
    assert window.chat.toPlainText() == before
    assert window.chat_jump_end.isEnabled()


def test_m124_confirmed_new_conversation_keeps_navigation_usable(host, monkeypatch) -> None:
    window, provider, _ = host
    _long_chat(window)
    window.chat_follow.setChecked(False)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window._context.snapshot() == ()
    assert window.chat_follow.isChecked()
    assert window.chat_jump_start.isEnabled()
    assert window.chat_jump_end.isEnabled()
    window.chat_jump_start.click()
    window.chat_jump_end.click()
    assert provider.calls == 0


def test_m124_two_windows_keep_scroll_and_follow_state_isolated(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory route
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        first = _long_chat(window)
        second = _long_chat(other)
        other.chat_follow.setChecked(False)
        other.chat_jump_start.click()
        window.chat_jump_end.click()
        assert first.value() == first.maximum()
        assert second.value() == second.minimum()
        assert window.chat_follow.isChecked()
        assert not other.chat_follow.isChecked()
    finally:
        other.close()
