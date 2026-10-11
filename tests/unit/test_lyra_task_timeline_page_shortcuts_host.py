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

START = "Tarefa: iniciada · 0/4 etapas"
PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"


class ControlledProvider:
    provider_id = "fake"

    def __init__(self):
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="controlled", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("provider continuation forbidden")

    def reply(self, text, *, history=()):
        raise AssertionError("provider reply forbidden")


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
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    dry = DryPool()
    window._pool = dry  # type: ignore[assignment]
    try:
        yield window, provider, memory, dry
    finally:
        window.close()


def populate(window):
    for message, terminal in (
        (START, False),
        (PENDING, False),
        (CANCELLED, True),
        (FAILED, True),
    ):
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=message, terminal=terminal)
        )
    window._refresh_task_timeline()


def snapshot(window):
    timeline = window._task_timeline
    return (
        timeline.snapshot(), timeline.summary(),
        timeline.interruption_count_label(),
        timeline.interruption_breakdown_label(),
    )



def populate_twelve(window):
    for index in range(12):
        message, terminal = (
            (START, False), (PENDING, False),
            (CANCELLED, True), (FAILED, True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=message, terminal=terminal)
        )
    window._refresh_task_timeline()




def create_view(window):
    populate_twelve(window)
    window.show()
    QApplication.processEvents()
    view=window.task_timeline_view
    view.show()
    QApplication.processEvents()
    bar=view.verticalScrollBar()
    assert bar.maximum()>bar.minimum()
    assert bar.pageStep()>=1
    return view,bar


def page(window,direction):
    button=(window.task_timeline_page_previous if direction<0
            else window.task_timeline_page_next)
    button.click()
    QApplication.processEvents()


def check_safe(window, provider, memory, dry, before):
    assert snapshot(window)==before
    assert window._memory is memory
    assert provider.calls==0
    assert not dry.workers
    assert window.task_timeline_view.isReadOnly()



MODS = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def m161_keyboard(window, key, widget=None, modifiers=MODS):
    target = window.input if widget is None else widget
    window.activateWindow()
    QApplication.processEvents()
    target.setFocus()
    QApplication.processEvents()
    assert target.hasFocus() or (
        target in (window.chat, window.task_timeline_view)
        and target.viewport().hasFocus()
    )
    QTest.keyClick(target, key, modifiers)
    QApplication.processEvents()


def m161_visible(window):
    view, bar = create_view(window)
    assert not view.isHidden() and bar.maximum() > bar.minimum()
    return bar


def m161_expected(bar, direction):
    step = max(1, bar.pageStep())
    return max(bar.minimum(), min(bar.maximum(), bar.value() + direction * step))


def test_m161_shortcut_identity_scope_enabled_and_model(host):
    window, provider, memory, dry = host
    for name, sequence in (
        ('page_previous', 'Ctrl+Shift+PgUp'),
        ('page_next', 'Ctrl+Shift+PgDown'),
    ):
        shortcut = getattr(window, 'task_timeline_' + name + '_shortcut')
        assert isinstance(shortcut, QShortcut)
        assert shortcut.parent() is window and shortcut.isEnabled()
        assert shortcut.objectName() == 'lyra_task_timeline_' + name + '_shortcut'
        assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
        assert shortcut.key() == QKeySequence(sequence)
    check_safe(window, provider, memory, dry, snapshot(window))


@pytest.mark.parametrize('direction', [-1, 1])
def test_m161_activation_signal_reveals_hidden_panel_with_exact_step(host, direction):
    window, provider, memory, dry = host
    populate_twelve(window)
    window.show()
    QApplication.processEvents()
    before = snapshot(window)
    assert window.task_timeline_view.isHidden()
    shortcut = (window.task_timeline_page_previous_shortcut if direction == -1
                else window.task_timeline_page_next_shortcut)
    shortcut.activated.emit()
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('focus_name', ['input', 'transcript_find', 'chat', 'task_timeline_view'])
@pytest.mark.parametrize('key,direction', [
    (Qt.Key.Key_PageUp, -1), (Qt.Key.Key_PageDown, 1),
])
def test_m161_real_qt_keys_from_four_focus_targets(host, focus_name, key, direction):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.maximum() if direction == -1 else bar.minimum())
    before = snapshot(window)
    expected = m161_expected(bar, direction)
    target = getattr(window, focus_name)
    m161_keyboard(window, key, target)
    assert bar.value() == expected
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('key,direction', [
    (Qt.Key.Key_PageUp, -1), (Qt.Key.Key_PageDown, 1),
])
def test_m161_real_keys_repeat_clamped_at_boundaries(host, key, direction):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.minimum() if direction == -1 else bar.maximum())
    before = snapshot(window)
    for _ in range(3):
        m161_keyboard(window, key)
    assert bar.value() == (bar.minimum() if direction == -1 else bar.maximum())
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('key,direction', [
    (Qt.Key.Key_PageUp, -1), (Qt.Key.Key_PageDown, 1),
])
def test_m161_disabled_shortcut_guards_signal_direct_and_input_key(host, key, direction):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.maximum() if direction == -1 else bar.minimum())
    old = bar.value()
    before = snapshot(window)
    shortcut = (window.task_timeline_page_previous_shortcut if direction == -1
                else window.task_timeline_page_next_shortcut)
    shortcut.setEnabled(False)
    try:
        shortcut.activated.emit()
        (window._page_task_timeline_previous_shortcut() if direction == -1
         else window._page_task_timeline_next_shortcut())
        m161_keyboard(window, key)
        assert bar.value() == old
    finally:
        shortcut.setEnabled(True)
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('key,direction', [
    (Qt.Key.Key_PageUp, -1), (Qt.Key.Key_PageDown, 1),
])
def test_m161_disabled_page_button_blocks_signal_and_direct(host, key, direction):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.maximum() if direction == -1 else bar.minimum())
    before = snapshot(window)
    old = bar.value()
    button = (window.task_timeline_page_previous if direction == -1
              else window.task_timeline_page_next)
    button.setEnabled(False)
    try:
        m161_keyboard(window, key)
        (window._page_task_timeline_previous_shortcut() if direction == -1
         else window._page_task_timeline_next_shortcut())
        assert bar.value() == old
    finally:
        button.setEnabled(True)
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('direction', [-1, 1])
def test_m161_disabled_timeline_blocks_signal_direct(host, direction):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.maximum() if direction == -1 else bar.minimum())
    old = bar.value()
    before = snapshot(window)
    window.task_timeline_view.setEnabled(False)
    try:
        shortcut = (window.task_timeline_page_previous_shortcut if direction == -1
                    else window.task_timeline_page_next_shortcut)
        shortcut.activated.emit()
        (window._page_task_timeline_previous_shortcut() if direction == -1
         else window._page_task_timeline_next_shortcut())
        assert bar.value() == old
    finally:
        window.task_timeline_view.setEnabled(True)
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('key', [Qt.Key.Key_PageUp, Qt.Key.Key_PageDown])
@pytest.mark.parametrize('modifiers', [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier,
                                       Qt.KeyboardModifier.ShiftModifier])
def test_m161_unmodified_and_partial_modifiers_do_not_hijack_composer(host, key, modifiers):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    bar.setValue(bar.maximum() // 2)
    before = snapshot(window)
    old = bar.value()
    m161_keyboard(window, key, modifiers=modifiers)
    assert bar.value() == old
    check_safe(window, provider, memory, dry, before)


@pytest.mark.parametrize('category', [0, 1, 2, 3])
def test_m161_filter_categories_remain_unchanged(host, category):
    window, provider, memory, dry = host
    m161_visible(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    window.task_timeline_interruptions_only.setChecked(True)
    before = snapshot(window)
    presentation = (
        window.task_timeline_view.toPlainText(),
        window.task_timeline_visible_count.text(),
        window.task_timeline_view_scope.text(),
    )
    for key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
        m161_keyboard(window, key)
    assert presentation == (
        window.task_timeline_view.toPlainText(),
        window.task_timeline_visible_count.text(),
        window.task_timeline_view_scope.text(),
    )
    check_safe(window, provider, memory, dry, before)


def test_m161_existing_first_last_routes_remain_compatible(host):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    before = snapshot(window)
    window.task_timeline_jump_first_shortcut.activated.emit()
    assert bar.value() == bar.minimum()
    m161_keyboard(window, Qt.Key.Key_PageDown)
    assert bar.value() > bar.minimum()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert bar.value() == bar.maximum()
    m161_keyboard(window, Qt.Key.Key_PageUp)
    assert bar.value() < bar.maximum()
    check_safe(window, provider, memory, dry, before)


def test_m161_two_windows_signal_isolation(host):
    window, provider, memory, dry = host
    other = MainWindow(ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog())
    try:
        left = m161_visible(window)
        right = m161_visible(other)
        left.setValue(left.minimum())
        right.setValue(right.maximum())
        other_old = right.value()
        window.task_timeline_page_next_shortcut.activated.emit()
        assert left.value() > left.minimum()
        assert right.value() == other_old
        check_safe(window, provider, memory, dry, snapshot(window))
    finally:
        other.close()


def test_m161_busy_dry_mode_only_presentation(host):
    window, provider, memory, dry = host
    m161_visible(window)
    window._start_tool_task('simulação', ())
    assert not window.input.isEnabled() and len(dry.workers) == 1
    populate_twelve(window)
    QApplication.processEvents()
    before_calls = provider.calls
    before_workers = len(dry.workers)
    window.task_timeline_page_previous_shortcut.activated.emit()
    window.task_timeline_page_next_shortcut.activated.emit()
    assert provider.calls == before_calls == 0
    assert len(dry.workers) == before_workers == 1
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()


@pytest.mark.parametrize('accepted', [False, True])
def test_m161_reset_keeps_shortcuts_and_correct_history(host, monkeypatch, accepted):
    window, provider, memory, dry = host
    bar = m161_visible(window)
    before = snapshot(window)
    monkeypatch.setattr(QMessageBox, 'question', lambda *_a, **_k: (
        QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No))
    window.session_reset.click()
    if accepted:
        assert window._task_timeline.snapshot() == ()
    else:
        assert snapshot(window) == before
    window.task_timeline_page_previous_shortcut.activated.emit()
    window.task_timeline_page_next_shortcut.activated.emit()
    assert bar.minimum() <= bar.value() <= bar.maximum()
    assert window.task_timeline_page_previous_shortcut.isEnabled()
    assert window.task_timeline_page_next_shortcut.isEnabled()
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers


def test_m161_malformed_category_remains_safe(host):
    window, provider, memory, dry = host
    m161_visible(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setItemData(0, 'RAW_SECRET')
    window._refresh_task_timeline()
    old = window.task_timeline_view.toPlainText()
    before = snapshot(window)
    window.task_timeline_page_previous_shortcut.activated.emit()
    window.task_timeline_page_next_shortcut.activated.emit()
    assert window.task_timeline_view.toPlainText() == old
    assert 'RAW_SECRET' not in old
    check_safe(window, provider, memory, dry, before)
