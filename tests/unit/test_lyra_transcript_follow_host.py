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
        memory_marker,  # type: ignore[arg-type] -- memory route not exercised
        provider,
        build_default_tool_catalog(),
    )
    window.resize(760, 360)
    window.show()
    app.processEvents()
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def _scrollable(window: MainWindow) -> None:
    window._lyra("\n".join(f"Linha {i:04d}" for i in range(240)))
    QApplication.processEvents()
    assert window.chat.verticalScrollBar().maximum() > 0


def test_m121_checkbox_is_checked_by_default(host) -> None:
    window, _, _ = host
    assert window.chat_follow.objectName() == "lyra_chat_follow"
    assert window.chat_follow.isChecked()
    assert window.chat.isReadOnly()


def test_m121_assistant_append_follows_when_enabled(host) -> None:
    window, _, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(0)
    window._lyra("Mensagem final")
    QApplication.processEvents()
    assert bar.value() == bar.maximum()


def test_m121_user_append_follows_when_enabled(host) -> None:
    window, _, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(0)
    window._you("Pedido final")
    QApplication.processEvents()
    assert bar.value() == bar.maximum()


def test_m121_assistant_append_keeps_position_when_disabled(host) -> None:
    window, _, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    window.chat_follow.setChecked(False)
    bar.setValue(0)
    window._lyra("Resposta posterior")
    QApplication.processEvents()
    assert bar.value() == 0
    assert "Resposta posterior" in window.chat.toPlainText()


def test_m121_user_append_keeps_position_when_disabled(host) -> None:
    window, _, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    window.chat_follow.setChecked(False)
    bar.setValue(0)
    window._you("Pedido posterior")
    QApplication.processEvents()
    assert bar.value() == 0
    assert "Pedido posterior" in window.chat.toPlainText()


def test_m121_tool_progress_uses_same_scroll_policy(host) -> None:
    window, provider, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    window.chat_follow.setChecked(False)
    bar.setValue(0)
    window._on_tool_progress("Etapa observada")
    QApplication.processEvents()
    assert bar.value() == 0
    assert provider.calls == 0
    assert window._context.snapshot()[-1].text == "Etapa observada"


def test_m121_reenable_jumps_to_bottom_without_mutating_chat(host) -> None:
    window, provider, _ = host
    _scrollable(window)
    bar = window.chat.verticalScrollBar()
    window.chat_follow.setChecked(False)
    bar.setValue(0)
    text = window.chat.toPlainText()
    history = window._context.snapshot()
    window.chat_follow.setChecked(True)
    QApplication.processEvents()
    assert bar.value() == bar.maximum()
    assert window.chat.toPlainText() == text
    assert window._context.snapshot() == history
    assert provider.calls == 0


def test_m121_toggle_is_passive_and_local(host) -> None:
    window, provider, memory_marker = host
    before = (window._context.snapshot(), window._perception.snapshot())
    style = window._personality.snapshot()
    window.chat_follow.setChecked(False)
    window.chat_follow.setChecked(True)
    assert (window._context.snapshot(), window._perception.snapshot()) == before
    assert window._personality.snapshot() == style
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m121_toggle_stays_available_during_busy_task(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    try:
        assert not window.send.isEnabled()
        assert not window.session_reset.isEnabled()
        assert window.chat_follow.isEnabled()
        window.chat_follow.click()
        assert not window.chat_follow.isChecked()
        assert provider.calls == 0
    finally:
        window._set_busy(False)


def test_m121_denied_reset_preserves_user_choice(host, monkeypatch) -> None:
    window, _, _ = host
    window._lyra("Manter conversa")
    window.chat_follow.setChecked(False)
    original = window.chat.toPlainText()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    assert not window.chat_follow.isChecked()
    assert window.chat.toPlainText() == original


def test_m121_confirmed_reset_restores_follow_default(host, monkeypatch) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Pedido da sessão")
    style = window._personality.snapshot()
    window.chat_follow.setChecked(False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert window.chat_follow.isChecked()
    assert window._context.snapshot() == ()
    assert window._perception.snapshot() == ()
    assert "Nova conversa iniciada." in window.chat.toPlainText()
    assert window._personality.snapshot() == style
    assert window._memory is memory_marker
    assert provider.calls == 0


def test_m121_follow_state_is_per_host(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- memory route not exercised
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window.chat_follow.setChecked(False)
        assert not window.chat_follow.isChecked()
        assert other.chat_follow.isChecked()
        other.chat_follow.setChecked(False)
        window.chat_follow.setChecked(True)
        assert window.chat_follow.isChecked()
        assert not other.chat_follow.isChecked()
    finally:
        other.close()
