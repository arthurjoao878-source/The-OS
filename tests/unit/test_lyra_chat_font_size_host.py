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
        raise AssertionError("unexpected tool continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected direct reply")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory_marker = object()
    window = MainWindow(
        ActionRegistry(),
        memory_marker,  # type: ignore[arg-type] -- memory route not used
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory_marker
    finally:
        window.close()


def test_m122_control_is_explicit_finite_and_defaults_to_system(host) -> None:
    window, _, _ = host
    control = window.chat_text_size
    assert control.objectName() == "lyra_chat_text_size"
    assert control.count() == 4
    assert [(control.itemText(i), control.itemData(i)) for i in range(4)] == [
        ("Sistema", None),
        ("Pequeno", 10),
        ("Normal", 12),
        ("Grande", 16),
    ]
    assert control.currentIndex() == 0
    assert window.chat.isReadOnly()


def test_m122_default_retains_host_system_font(host) -> None:
    window, _, _ = host
    assert window.chat.font() == window._chat_base_font
    assert window.chat_text_size.currentData() is None


def test_m122_small_normal_large_apply_exact_finite_sizes(host) -> None:
    window, _, _ = host
    for label, size in (("Pequeno", 10), ("Normal", 12), ("Grande", 16)):
        index = window.chat_text_size.findText(label)
        assert index >= 0
        window.chat_text_size.setCurrentIndex(index)
        assert window.chat.font().pointSize() == size


def test_m122_system_restores_original_font_without_data_loss(host) -> None:
    window, _, _ = host
    window._lyra("Texto existente no chat")
    original_text = window.chat.toPlainText()
    original_font = window._chat_base_font
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
    window.chat_text_size.setCurrentIndex(0)
    assert window.chat.font() == original_font
    assert window.chat.toPlainText() == original_text


def test_m122_invalid_injected_combo_data_fails_closed(host) -> None:
    window, _, _ = host
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(12))
    before = window.chat.font()
    window.chat_text_size.addItem("Invalid", 999)
    window.chat_text_size.setCurrentIndex(window.chat_text_size.count() - 1)
    assert window.chat.font() == before
    window.chat_text_size.addItem("Non-integer", "16")
    window.chat_text_size.setCurrentIndex(window.chat_text_size.count() - 1)
    assert window.chat.font() == before


def test_m122_only_transcript_font_changes_not_composer_or_find(host) -> None:
    window, _, _ = host
    input_font = window.input.font()
    find_font = window.transcript_find.font()
    window.input.setText("Rascunho privado")
    window.transcript_find.setText("termo")
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
    assert window.input.font() == input_font
    assert window.transcript_find.font() == find_font
    assert window.input.text() == "Rascunho privado"
    assert window.transcript_find.text() == "termo"


def test_m122_font_changes_are_passive_no_provider_or_context_mutation(host) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Pedido existente")
    window._lyra("Resposta existente")
    before_context = window._context.snapshot()
    before_perception = window._perception.snapshot()
    before_personality = window._personality.snapshot()
    before_chat = window.chat.toPlainText()
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(10))
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
    assert provider.calls == 0
    assert window._context.snapshot() == before_context
    assert window._perception.snapshot() == before_perception
    assert window._personality.snapshot() == before_personality
    assert window._memory is memory_marker
    assert window.chat.toPlainText() == before_chat


def test_m122_font_change_available_while_host_busy(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    try:
        assert not window.send.isEnabled()
        assert window.chat_text_size.isEnabled()
        window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
        assert window.chat.font().pointSize() == 16
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.chat_text_size.isEnabled()


def test_m122_denied_reset_preserves_font_and_temporary_context(
    host, monkeypatch
) -> None:
    window, _, _ = host
    window._context.add_user("Manter")
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
    before = window._context.snapshot()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.chat.font().pointSize() == 16
    assert window._context.snapshot() == before


def test_m122_confirmed_reset_restores_system_without_persistence(
    host, monkeypatch
) -> None:
    window, provider, memory_marker = host
    window._context.add_user("Temporario")
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
    personality_before = window._personality.snapshot()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.chat_text_size.currentIndex() == 0
    assert window.chat.font() == window._chat_base_font
    assert window._context.snapshot() == ()
    assert window._memory is memory_marker
    assert window._personality.snapshot() == personality_before
    assert provider.calls == 0


def test_m122_two_hosts_keep_font_controls_isolated(host) -> None:
    window, _, _ = host
    other = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- memory route not used
        CaptureProvider(),
        build_default_tool_catalog(),
    )
    try:
        window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(16))
        assert window.chat.font().pointSize() == 16
        assert other.chat_text_size.currentIndex() == 0
        assert other.chat.font() == other._chat_base_font
    finally:
        other.close()


def test_m122_existing_find_and_draft_recall_still_operate(host) -> None:
    window, provider, _ = host
    window._context.add_user("Pedido antigo")
    window._lyra("Palavra para localizar")
    window.chat_text_size.setCurrentIndex(window.chat_text_size.findData(10))
    window.transcript_find.setText("Palavra")
    window.transcript_find_next.click()
    assert window.chat.textCursor().selectedText() == "Palavra"
    window.draft_previous.click()
    assert window.input.text() == "Pedido antigo"
    assert provider.calls == 0
