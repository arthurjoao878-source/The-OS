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
        ActionRegistry(), memory_marker,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def find_positions(window, *, backward: bool = False) -> str:
    shortcut = (
        window.transcript_find_enter_previous_shortcut
        if backward else window.transcript_find_enter_next_shortcut
    )
    shortcut.activated.emit()
    return window.transcript_match_position.text()


def test_m132_shortcut_identity_parent_and_scope(host) -> None:
    window, provider, _ = host
    next_key = window.transcript_find_enter_next_shortcut
    previous_key = window.transcript_find_enter_previous_shortcut
    assert next_key.objectName() == "lyra_transcript_find_enter_next_shortcut"
    assert previous_key.objectName() == "lyra_transcript_find_enter_previous_shortcut"
    assert next_key.parent() is window.transcript_find
    assert previous_key.parent() is window.transcript_find
    assert next_key.context() == Qt.ShortcutContext.WidgetShortcut
    assert previous_key.context() == Qt.ShortcutContext.WidgetShortcut
    assert next_key.key() == QKeySequence("Return")
    assert previous_key.key() == QKeySequence("Shift+Return")
    assert next_key.isEnabled() and previous_key.isEnabled()
    assert provider.calls == 0


def test_m132_enter_uses_existing_next_handler(host) -> None:
    window, provider, _ = host
    window._lyra("quartz quartz")
    window.transcript_find.setText("quartz")
    assert find_positions(window) == "Posição: 1 de 2"
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.chat.textCursor().selectedText() == "quartz"
    assert provider.calls == 0


def test_m132_shift_enter_uses_existing_previous_handler(host) -> None:
    window, provider, _ = host
    window._lyra("quartz quartz")
    window.transcript_find.setText("quartz")
    assert find_positions(window, backward=True) == "Posição: 2 de 2"
    assert window.chat.textCursor().selectedText() == "quartz"
    assert provider.calls == 0


def test_m132_enter_navigation_wraps_without_extra_scan(host) -> None:
    window, provider, _ = host
    window._lyra("gold gold")
    window.transcript_find.setText("gold")
    assert find_positions(window) == "Posição: 1 de 2"
    assert find_positions(window) == "Posição: 2 de 2"
    assert find_positions(window) == "Posição: 1 de 2"
    assert provider.calls == 0


def test_m132_shift_enter_navigation_wraps(host) -> None:
    window, provider, _ = host
    window._lyra("blue blue")
    window.transcript_find.setText("blue")
    assert find_positions(window, backward=True) == "Posição: 2 de 2"
    assert find_positions(window, backward=True) == "Posição: 1 de 2"
    assert find_positions(window, backward=True) == "Posição: 2 de 2"
    assert provider.calls == 0


def test_m132_enter_uses_case_and_whole_word_modes(host) -> None:
    window, provider, _ = host
    window._lyra("Oak oak Oakley")
    window.transcript_find.setText("Oak")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    assert find_positions(window) == "Posição: 1 de 1"
    assert window.transcript_match_count.text() == "Ocorrências: 1"
    assert find_positions(window, backward=True) == "Posição: 1 de 1"
    assert provider.calls == 0


def test_m132_shortcuts_preserve_query_draft_and_modes(host) -> None:
    window, provider, _ = host
    window._lyra("word word")
    window.input.setText("mensagem não enviada")
    window.transcript_find.setText("word")
    window.transcript_find_whole_word.setChecked(True)
    find_positions(window)
    find_positions(window, backward=True)
    assert window.input.text() == "mensagem não enviada"
    assert window.transcript_find.text() == "word"
    assert window.transcript_find_whole_word.isChecked()
    assert provider.calls == 0


def test_m132_empty_find_is_safe_and_does_not_submit(host) -> None:
    window, provider, _ = host
    window.input.setText("unsent")
    assert find_positions(window) == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: informe termo"
    assert find_positions(window, backward=True) == "Posição: —"
    assert window.input.text() == "unsent"
    assert provider.calls == 0


def test_m132_manual_buttons_and_f3_remain_compatible(host) -> None:
    window, provider, _ = host
    window._lyra("mars mars mars")
    window.transcript_find.setText("mars")
    assert find_positions(window) == "Posição: 1 de 3"
    window.transcript_find_next.click()
    assert window.transcript_match_position.text() == "Posição: 2 de 3"
    window.transcript_find_next_shortcut.activated.emit()
    assert window.transcript_match_position.text() == "Posição: 3 de 3"
    assert find_positions(window, backward=True) == "Posição: 2 de 3"
    assert provider.calls == 0


def test_m132_busy_shortcuts_and_direct_handlers_are_guarded(host) -> None:
    window, provider, _ = host
    window._lyra("busy busy")
    window.transcript_find.setText("busy")
    previous = window.chat.textCursor().selectionStart()
    window._set_busy(True)
    try:
        assert not window.transcript_find_enter_next_shortcut.isEnabled()
        assert not window.transcript_find_enter_previous_shortcut.isEnabled()
        assert not window.transcript_find.isEnabled()
        window._find_next_in_transcript()
        window._find_previous_in_transcript()
        assert window.chat.textCursor().selectionStart() == previous
        assert window.transcript_match_count.text() == "Ocorrências: —"
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_enter_next_shortcut.isEnabled()
    assert window.transcript_find_enter_previous_shortcut.isEnabled()


def test_m132_widget_scope_and_escape_compatibility(host) -> None:
    window, provider, _ = host
    window.show()
    window.transcript_find.setText("hold")
    window.transcript_find.setFocus()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    window.transcript_find_escape_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.input.hasFocus()
    assert window.transcript_find.text() == "hold"
    assert window.transcript_find_enter_next_shortcut.parent() is window.transcript_find
    assert provider.calls == 0


def test_m132_clear_stays_explicit(host) -> None:
    window, provider, _ = host
    window._lyra("clear clear")
    window.transcript_find.setText("clear")
    find_positions(window)
    assert window.transcript_find.text() == "clear"
    window.transcript_find_clear.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_find_enter_next_shortcut.isEnabled()
    assert provider.calls == 0


def test_m132_window_local_shortcut_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window._lyra("apple apple")
        window.transcript_find.setText("apple")
        other.transcript_find.setText("other")
        find_positions(window)
        assert other.transcript_find.text() == "other"
        assert other.transcript_match_count.text() == "Ocorrências: —"
        assert window.transcript_find_enter_next_shortcut is not (
            other.transcript_find_enter_next_shortcut
        )
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m132_reset_denied_and_accepted_keep_shortcuts(host, monkeypatch) -> None:
    window, provider, memory = host
    window.transcript_find.setText("hold")
    personality = window._personality.snapshot()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == "hold"
    assert window.transcript_find_enter_next_shortcut.isEnabled()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.transcript_find.text() == ""
    assert window.transcript_find_enter_previous_shortcut.isEnabled()
    assert window._personality.snapshot() == personality
    assert window._memory is memory
    assert provider.calls == 0


def test_m132_keypad_shortcuts_have_strict_widget_scope(host) -> None:
    window, provider, _ = host
    next_key = window.transcript_find_keypad_enter_next_shortcut
    prev_key = window.transcript_find_keypad_enter_previous_shortcut
    assert next_key.objectName() == "lyra_transcript_find_keypad_enter_next_shortcut"
    assert (
        prev_key.objectName()
        == "lyra_transcript_find_keypad_enter_previous_shortcut"
    )
    assert next_key.parent() is window.transcript_find
    assert prev_key.parent() is window.transcript_find
    assert next_key.context() == Qt.ShortcutContext.WidgetShortcut
    assert prev_key.context() == Qt.ShortcutContext.WidgetShortcut
    assert next_key.key() == QKeySequence(Qt.Key.Key_Enter)
    assert prev_key.key() == QKeySequence("Shift+Enter")
    assert next_key.isEnabled() and prev_key.isEnabled()
    assert provider.calls == 0


def test_m132_keypad_enter_real_qt_key_event_wraps(host) -> None:
    window, provider, _ = host
    window.show()
    window._lyra("zephyr zephyr zephyr")
    window.transcript_find.setText("zephyr")
    window.transcript_find.setFocus()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    ranks = ("Posição: 1 de 3", "Posição: 2 de 3",
             "Posição: 3 de 3", "Posição: 1 de 3")
    for expected in ranks:
        QTest.keyClick(window.transcript_find, Qt.Key.Key_Enter)
        QApplication.processEvents()
        assert window.transcript_match_position.text() == expected
    assert window.transcript_match_count.text() == "Ocorrências: 3"
    assert provider.calls == 0


def test_m132_shift_keypad_enter_real_qt_key_event_wraps(host) -> None:
    window, provider, _ = host
    window.show()
    window._lyra("lychee lychee lychee")
    window.transcript_find.setText("lychee")
    window.transcript_find.setFocus()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    ranks = ("Posição: 3 de 3", "Posição: 2 de 3",
             "Posição: 1 de 3", "Posição: 3 de 3")
    for expected in ranks:
        QTest.keyClick(
            window.transcript_find, Qt.Key.Key_Enter,
            Qt.KeyboardModifier.ShiftModifier,
        )
        QApplication.processEvents()
        assert window.transcript_match_position.text() == expected
    assert provider.calls == 0


def test_m132_keypad_busy_direct_and_window_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window._lyra("apple apple")
        window.transcript_find.setText("apple")
        other.transcript_find.setText("apple")
        window.transcript_find_keypad_enter_next_shortcut.activated.emit()
        assert window.transcript_match_position.text() == "Posição: 1 de 2"
        assert other.transcript_match_position.text() == "Posição: —"
        window._set_busy(True)
        try:
            assert not window.transcript_find_keypad_enter_next_shortcut.isEnabled()
            assert not window.transcript_find_keypad_enter_previous_shortcut.isEnabled()
            before = window.transcript_match_position.text()
            window._find_next_in_transcript()
            window._find_previous_in_transcript()
            assert window.transcript_match_position.text() == before
        finally:
            window._set_busy(False)
        assert window.transcript_find_keypad_enter_next_shortcut.isEnabled()
        assert window.transcript_find_keypad_enter_previous_shortcut.isEnabled()
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()
