from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView


class ControlledProvider:
    provider_id = "fake"

    def __init__(self):
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("continuation is not allowed")

    def reply(self, text, *, history=()):
        raise AssertionError("reply is not allowed")


class DryPool:
    def __init__(self):
        self.workers = []

    def start(self, worker):
        self.workers.append(worker)


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = ControlledProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory, provider, build_default_tool_catalog()
    )
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def populate(window):
    for index in range(12):
        message, terminal = (
            ("Tarefa: iniciada · 0/4 etapas", False),
            ("Tarefa: cancelamento solicitado · aguardando confirmação", False),
            ("Tarefa: cancelada · 0/4 etapas", True),
            ("Tarefa: falhou · 1/4 etapas · sistema", True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=message, terminal=terminal)
        )
    window._refresh_task_timeline()


def make_visible(window):
    populate(window)
    window.show()
    QApplication.processEvents()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    return bar


def snapshot(window):
    t = window._task_timeline
    return (
        t.snapshot(), t.summary(), t.interruption_count_label(),
        t.interruption_breakdown_label(),
        window.task_timeline_interruptions_only.isChecked(),
        window.task_timeline_interruption_category.currentIndex(),
        window.task_timeline_interruption_category.currentData(),
    )


def passive(window, provider, memory, dry, state):
    assert snapshot(window) == state
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert not dry.workers


def real_focus(window, target):
    window.activateWindow()
    QApplication.processEvents()
    target.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        target, Qt.Key.Key_H,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def position(window):
    bar = window.task_timeline_view.verticalScrollBar()
    return bar.value(), window.task_timeline_scroll_position.text()


def press_from_composer(window):
    real_focus(window, window.input)


def test_m165_shortcut_identity_and_default_state(host):
    window, provider, memory, dry = host
    shortcut = window.task_timeline_focus_shortcut
    assert isinstance(shortcut, QShortcut)
    assert shortcut.key() == QKeySequence("Ctrl+Shift+H")
    assert shortcut.objectName() == "lyra_task_timeline_focus_shortcut"
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.parent() is window
    assert shortcut.isEnabled()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    passive(window, provider, memory, dry, snapshot(window))


def test_m165_hidden_panel_revealed_with_real_qt_key(host):
    window, provider, memory, dry = host
    window.show()
    QApplication.processEvents()
    before = snapshot(window)
    assert window.task_timeline_view.isHidden()
    press_from_composer(window)
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.hasFocus()
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("target_name", (
    "input", "transcript_find", "chat", "task_timeline_view",
))
def test_m165_real_key_focus_from_four_widgets(host, target_name):
    window, provider, memory, dry = host
    bar = make_visible(window)
    target = getattr(window, target_name)
    target.setFocus()
    QApplication.processEvents()
    bar.setValue(bar.maximum())
    before = snapshot(window)
    old_position = position(window)
    real_focus(window, target)
    assert window.task_timeline_view.hasFocus()
    assert position(window) == old_position
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("n", (1, 2, 8))
def test_m165_repeated_shortcut_focus_idempotent(host, n):
    window, provider, memory, dry = host
    bar = make_visible(window)
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    before = snapshot(window)
    old_position = position(window)
    for _ in range(n):
        press_from_composer(window)
        assert window.task_timeline_view.hasFocus()
        assert position(window) == old_position
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("category", (0, 1, 2, 3))
def test_m165_preserves_filtered_timeline_category_and_position(host, category):
    window, provider, memory, dry = host
    bar = make_visible(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    bar.setValue(bar.maximum())
    before = snapshot(window)
    old_position = position(window)
    press_from_composer(window)
    assert window.task_timeline_view.hasFocus()
    assert position(window) == old_position
    passive(window, provider, memory, dry, before)


def test_m165_find_draft_and_transcript_unchanged(host):
    window, provider, memory, dry = host
    make_visible(window)
    window.input.setText("RAScunHO Privado")
    window.transcript_find.setText("buscar eventos")
    window.chat.appendPlainText("mensagem pública")
    QApplication.processEvents()
    before = snapshot(window)
    draft, query, transcript = (
        window.input.text(), window.transcript_find.text(), window.chat.toPlainText()
    )
    real_focus(window, window.transcript_find)
    assert window.task_timeline_view.hasFocus()
    assert (window.input.text(), window.transcript_find.text(), window.chat.toPlainText()) == (
        draft, query, transcript
    )
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("control_name", (
    "task_timeline_focus_shortcut", "task_timeline_toggle", "task_timeline_view",
))
def test_m165_disabled_signal_direct_and_real_key_fail_closed(host, control_name):
    window, provider, memory, dry = host
    make_visible(window)
    window.input.setFocus()
    QApplication.processEvents()
    before = snapshot(window)
    control = getattr(window, control_name)
    control.setEnabled(False)
    try:
        window.task_timeline_focus_shortcut.activated.emit()
        window._focus_task_timeline_shortcut()
        assert window.input.hasFocus()
        real_focus(window, window.input)
        assert not window.task_timeline_view.hasFocus()
    finally:
        control.setEnabled(True)
    press_from_composer(window)
    assert window.task_timeline_view.hasFocus()
    passive(window, provider, memory, dry, before)


def test_m165_signal_and_direct_handler_equivalent(host):
    window, provider, memory, dry = host
    make_visible(window)
    before = snapshot(window)
    window.input.setFocus()
    window.task_timeline_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.task_timeline_view.hasFocus()
    window.input.setFocus()
    window._focus_task_timeline_shortcut()
    QApplication.processEvents()
    assert window.task_timeline_view.hasFocus()
    passive(window, provider, memory, dry, before)


def test_m165_no_window_global_shortcut_two_hosts_isolated(host):
    window, provider, memory, dry = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(), other_provider, build_default_tool_catalog()
    )
    try:
        make_visible(window)
        make_visible(other)
        other.input.setFocus()
        QApplication.processEvents()
        before = snapshot(window)
        other_before = snapshot(other)
        real_focus(window, window.input)
        assert window.task_timeline_view.hasFocus()
        assert not other.task_timeline_view.hasFocus()
        assert snapshot(other) == other_before
        real_focus(other, other.input)
        assert other.task_timeline_view.hasFocus()
        assert snapshot(window) == before
        assert provider.calls == 0 and other_provider.calls == 0
        passive(window, provider, memory, dry, before)
    finally:
        other.close()


def test_m165_busy_dry_worker_focus_only(host):
    window, provider, memory, dry = host
    make_visible(window)
    window._start_tool_task("simulação", ())
    assert len(dry.workers) == 1
    assert not window.input.isEnabled()
    bar = window.task_timeline_view.verticalScrollBar()
    bar.setValue(bar.maximum())
    before = snapshot(window)
    old_position = position(window)
    real_focus(window, window.task_timeline_view)
    assert window.task_timeline_view.hasFocus()
    assert position(window) == old_position
    assert snapshot(window) == before
    assert provider.calls == 0 and len(dry.workers) == 1
    assert window._memory is memory


@pytest.mark.parametrize("accepted", (False, True))
def test_m165_reset_retains_shortcut_and_focus(host, monkeypatch, accepted):
    window, provider, memory, dry = host
    make_visible(window)
    before = snapshot(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: (
        QMessageBox.StandardButton.Yes
        if accepted else QMessageBox.StandardButton.No
    ))
    window.session_reset.click()
    QApplication.processEvents()
    if accepted:
        assert window._task_timeline.snapshot() == ()
    else:
        assert snapshot(window) == before
    press_from_composer(window)
    assert window.task_timeline_view.hasFocus()
    assert window.task_timeline_focus_shortcut.isEnabled()
    assert provider.calls == 0 and not dry.workers
    assert window._memory is memory


@pytest.mark.parametrize("mods", (
    Qt.KeyboardModifier.NoModifier,
    Qt.KeyboardModifier.ControlModifier,
    Qt.KeyboardModifier.ShiftModifier,
))
def test_m165_plain_or_unrelated_h_not_hijacked(host, mods):
    window, provider, memory, dry = host
    make_visible(window)
    before = snapshot(window)
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.input, Qt.Key.Key_H, mods)
    QApplication.processEvents()
    assert not window.task_timeline_view.hasFocus()
    passive(window, provider, memory, dry, before)
