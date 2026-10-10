from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
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
        raise AssertionError("unexpected continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected direct provider reply")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory
    finally:
        window.close()


def focus(window, widget) -> None:
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    widget.setFocus()
    QApplication.processEvents()
    assert widget.hasFocus()


def press_jump_start(widget) -> None:
    QTest.keyClick(
        widget, Qt.Key.Key_K,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def fill_history(window) -> None:
    window.show()
    window.resize(780, 450)
    window._lyra("\n".join(f"linha {i}" for i in range(180)))
    QApplication.processEvents()
    assert window.chat.verticalScrollBar().maximum() > 0


def test_m141_identity_and_window_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.chat_jump_start_shortcut
    assert shortcut.objectName() == "lyra_chat_jump_start_shortcut"
    assert shortcut.parent() is window
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.key() == QKeySequence("Ctrl+Shift+K")
    assert shortcut.isEnabled() and provider.calls == 0


def test_m141_direct_handler_to_start(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window._jump_to_chat_start_shortcut()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_signal_to_start(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window.chat_jump_start_shortcut.activated.emit()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_real_qt_composer_keeps_draft_focus(host) -> None:
    window, provider, _ = host
    fill_history(window)
    window.input.setText("rascunho local")
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    focus(window, window.input)
    press_jump_start(window.input)
    assert bar.value() == bar.minimum()
    assert window.input.hasFocus() and window.input.text() == "rascunho local"
    assert provider.calls == 0


def test_m141_real_qt_find_preserves_search(host) -> None:
    window, provider, _ = host
    fill_history(window)
    window.transcript_find.setText("linha")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    focus(window, window.transcript_find)
    press_jump_start(window.transcript_find)
    assert bar.value() == bar.minimum()
    assert window.transcript_find.hasFocus()
    assert window.transcript_find.text() == "linha"
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert provider.calls == 0


def test_m141_real_qt_transcript_readonly(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    focus(window, window.chat)
    press_jump_start(window.chat)
    assert bar.value() == bar.minimum()
    assert window.chat.isReadOnly() and window.chat.hasFocus()
    assert provider.calls == 0


def test_m141_preserves_follow_off(host) -> None:
    window, provider, _ = host
    fill_history(window)
    window.chat_follow.setChecked(False)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window.chat_jump_start_shortcut.activated.emit()
    assert bar.value() == bar.minimum()
    assert not window.chat_follow.isChecked()
    window._lyra("novas mensagens")
    assert not window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m141_preserves_follow_on(host) -> None:
    window, provider, _ = host
    fill_history(window)
    assert window.chat_follow.isChecked()
    window.chat_jump_start_shortcut.activated.emit()
    assert window.chat_follow.isChecked()
    bar = window.chat.verticalScrollBar()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_existing_start_button_same_result(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window.chat_jump_start.click()
    assert bar.value() == bar.minimum()
    bar.setValue(bar.maximum())
    window.chat_jump_start_shortcut.activated.emit()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_repeated_navigation_idempotent(host) -> None:
    window, provider, _ = host
    fill_history(window)
    window.chat_jump_start_shortcut.activated.emit()
    window.chat_jump_start_shortcut.activated.emit()
    bar = window.chat.verticalScrollBar()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_busy_navigation_stays_available(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    window._set_busy(True)
    try:
        assert window.chat_jump_start_shortcut.isEnabled()
        bar.setValue(bar.maximum())
        window.chat_jump_start_shortcut.activated.emit()
        assert bar.value() == bar.minimum()
        bar.setValue(bar.maximum())
        window._jump_to_chat_start_shortcut()
        assert bar.value() == bar.minimum()
        assert provider.calls == 0
    finally:
        window._set_busy(False)


def test_m141_disabled_shortcut_direct_guard(host) -> None:
    window, provider, _ = host
    fill_history(window)
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window.chat_jump_start_shortcut.setEnabled(False)
    try:
        window._jump_to_chat_start_shortcut()
        assert bar.value() == bar.maximum()
    finally:
        window.chat_jump_start_shortcut.setEnabled(True)
    assert provider.calls == 0


def test_m141_two_window_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        fill_history(window)
        fill_history(other)
        bar = window.chat.verticalScrollBar()
        other_bar = other.chat.verticalScrollBar()
        bar.setValue(bar.maximum())
        other_bar.setValue(other_bar.maximum())
        window.chat_jump_start_shortcut.activated.emit()
        assert bar.value() == bar.minimum()
        assert other_bar.value() == other_bar.maximum()
        assert other.chat_jump_start_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m141_denied_reset_retains_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    fill_history(window)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.chat_jump_start_shortcut.isEnabled()
    bar = window.chat.verticalScrollBar()
    bar.setValue(bar.maximum())
    window.chat_jump_start_shortcut.activated.emit()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0


def test_m141_accepted_reset_keeps_navigation(host, monkeypatch) -> None:
    window, provider, memory = host
    fill_history(window)
    personality = window._personality.snapshot()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.chat_jump_start_shortcut.isEnabled()
    window._lyra("apos reset")
    window.chat_jump_start_shortcut.activated.emit()
    bar = window.chat.verticalScrollBar()
    assert bar.value() == bar.minimum()
    assert window._memory is memory
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m141_no_provider_memory_context_or_task_side_effect(host) -> None:
    window, provider, memory = host
    fill_history(window)
    before = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    transcript = window.chat.toPlainText()
    window.chat_jump_start_shortcut.activated.emit()
    assert window._context.provider_snapshot() == before
    assert window._personality.snapshot() == personality
    assert window._perception is perception
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
