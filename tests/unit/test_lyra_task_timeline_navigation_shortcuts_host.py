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



FIRST = Qt.Key.Key_Home
LAST = Qt.Key.Key_End
MODIFIERS = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def keyboard(window, key, target=None):
    widget = target if target is not None else window.input
    window.activateWindow()
    QApplication.processEvents()
    widget.setFocus()
    QTest.keyClick(widget, key, MODIFIERS)
    QApplication.processEvents()


def show_filled(window):
    populate_twelve(window)
    window.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    return bar


def test_m159_shortcut_identity_context_and_enabled(host):
    window, provider, _, dry = host
    first = window.task_timeline_jump_first_shortcut
    latest = window.task_timeline_jump_latest_shortcut
    assert isinstance(first, QShortcut) and isinstance(latest, QShortcut)
    assert first.parent() is window and latest.parent() is window
    assert first.objectName() == 'lyra_task_timeline_jump_first_shortcut'
    assert latest.objectName() == 'lyra_task_timeline_jump_latest_shortcut'
    assert first.key() == QKeySequence('Ctrl+Shift+Home')
    assert latest.key() == QKeySequence('Ctrl+Shift+End')
    assert first.context() == Qt.ShortcutContext.WindowShortcut
    assert latest.context() == Qt.ShortcutContext.WindowShortcut
    assert first.isEnabled() and latest.isEnabled()
    assert provider.calls == 0 and not dry.workers


def test_m159_signal_first_reveals_hidden_and_preserves_model(host):
    window, provider, memory, dry = host
    bar = show_filled(window)
    before = snapshot(window)
    assert window.task_timeline_view.isHidden()
    window.task_timeline_jump_first_shortcut.activated.emit()
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    assert bar.maximum() > 0 and bar.value() == bar.minimum()
    assert snapshot(window) == before
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m159_signal_latest_reveals_hidden_and_preserves_model(host):
    window, provider, _, dry = host
    bar = show_filled(window)
    before = snapshot(window)
    assert window.task_timeline_view.isHidden()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()
    assert snapshot(window) == before
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize('key,to_max', [(FIRST,False),(LAST,True)])
def test_m159_real_qt_composer_key_reveals_and_navigates(host,key,to_max):
    window, provider, _, dry = host
    bar = show_filled(window)
    window.input.setText('rascunho preservado')
    keyboard(window, key)
    assert not window.task_timeline_view.isHidden()
    assert bar.maximum() > bar.minimum()
    assert bar.value() == (bar.maximum() if to_max else bar.minimum())
    assert window.input.text() == 'rascunho preservado'
    assert provider.calls == 0 and not dry.workers


def test_m159_real_qt_first_latest_roundtrip(host):
    window, provider, _, dry = host
    bar=show_filled(window)
    keyboard(window, LAST)
    assert bar.value() == bar.maximum() and bar.maximum() > 0
    keyboard(window, FIRST)
    assert bar.value() == bar.minimum()
    keyboard(window, LAST)
    assert bar.value() == bar.maximum()
    keyboard(window, FIRST)
    assert bar.value() == bar.minimum()
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize('index', [0,1,2,3])
def test_m159_all_four_categories_preserve_filters_counts_and_history(host,index):
    window, provider, _, dry = host
    bar=show_filled(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(index)
    before=snapshot(window)
    count=window.task_timeline_visible_count.text()
    scope=window.task_timeline_view_scope.text()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    window.task_timeline_jump_first_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert bar.value() == bar.minimum()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex() == index
    assert (window.task_timeline_visible_count.text(),window.task_timeline_view_scope.text()) == (count,scope)
    assert snapshot(window)==before
    assert provider.calls==0 and not dry.workers


def test_m159_inert_category_filter_off_preserves_full_view(host):
    window,_,_,_=host
    show_filled(window)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    before=window.task_timeline_view.toPlainText()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    window.task_timeline_jump_first_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex()==3
    assert window.task_timeline_view.toPlainText()==before


@pytest.mark.parametrize('which', ['first','latest'])
def test_m159_disabled_shortcut_direct_signal_guard(host,which):
    window,provider,_,dry=host
    bar=show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar.setValue(bar.maximum()//2)
    before=bar.value()
    shortcut=getattr(window,'task_timeline_jump_'+which+'_shortcut')
    shortcut.setEnabled(False)
    try:
        shortcut.activated.emit()
        assert bar.value()==before
        assert provider.calls==0 and not dry.workers
    finally:
        shortcut.setEnabled(True)


@pytest.mark.parametrize('which', ['first','latest'])
def test_m159_disabled_button_direct_shortcut_guard(host,which):
    window,provider,_,dry=host
    bar=show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar.setValue(bar.maximum()//2)
    before=bar.value()
    button=getattr(window,'task_timeline_jump_'+which)
    button.setEnabled(False)
    try:
        getattr(window,'_jump_to_'+which+'_task_timeline_event_shortcut')()
        getattr(window,'task_timeline_jump_'+which+'_shortcut').activated.emit()
        assert bar.value()==before
        assert provider.calls==0 and not dry.workers
    finally:
        button.setEnabled(True)


def test_m159_disabled_timeline_blocks_both_keyboard_handlers(host):
    window,provider,_,dry=host
    bar=show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar.setValue(bar.maximum()//2)
    before=bar.value()
    window.task_timeline_view.setEnabled(False)
    try:
        window._jump_to_first_task_timeline_event_shortcut()
        window._jump_to_latest_task_timeline_event_shortcut()
        assert bar.value()==before
        assert provider.calls==0 and not dry.workers
    finally:
        window.task_timeline_view.setEnabled(True)


def test_m159_repeated_navigation_idempotent(host):
    window,provider,_,dry=host
    bar=show_filled(window)
    before=snapshot(window)
    for _ in range(3):
        window.task_timeline_jump_first_shortcut.activated.emit()
    assert bar.value()==bar.minimum()
    for _ in range(3):
        window.task_timeline_jump_latest_shortcut.activated.emit()
    assert bar.value()==bar.maximum()
    assert snapshot(window)==before
    assert provider.calls==0 and not dry.workers


def test_m159_two_window_isolation_real_qt(host):
    window,provider,memory,dry=host
    other=MainWindow(ActionRegistry(),object(),ControlledProvider(),build_default_tool_catalog())
    try:
        one=show_filled(window)
        two=show_filled(other)
        other.task_timeline_view.show()
        QApplication.processEvents()
        two.setValue(two.maximum())
        before=two.value()
        keyboard(window,FIRST)
        assert one.value()==one.minimum()
        assert two.value()==before
        assert other.task_timeline_jump_first_shortcut.parent() is other
        assert window._memory is memory and provider.calls==0 and not dry.workers
    finally:
        other.close()


def test_m159_busy_dry_task_no_dispatch(host):
    window,provider,_,dry=host
    bar=show_filled(window)
    window._start_tool_task('tarefa simulada', ())
    assert dry.workers and provider.calls==0
    pending=len(dry.workers)
    keyboard(window,LAST)
    keyboard(window,FIRST)
    assert bar.value()==bar.minimum()
    assert len(dry.workers)==pending and provider.calls==0


def test_m159_corrupted_category_never_leaks_untrusted_text(host):
    window,provider,_,dry=host
    show_filled(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    window.task_timeline_interruption_category.setItemData(1,'UNTRUSTED-MODE')
    window._refresh_task_timeline()
    before=window.task_timeline_view.toPlainText()
    window.task_timeline_jump_first_shortcut.activated.emit()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert window.task_timeline_view.toPlainText()==before
    assert 'UNTRUSTED-MODE' not in before
    assert provider.calls==0 and not dry.workers


def test_m159_accepted_reset_retains_shortcuts_without_task(host,monkeypatch):
    window,provider,memory,dry=host
    show_filled(window)
    monkeypatch.setattr(QMessageBox,'question',lambda *_args,**_kwargs: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert not window._task_timeline.snapshot()
    window.task_timeline_jump_first_shortcut.activated.emit()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    assert window._memory is memory and provider.calls==0 and not dry.workers


def test_m159_denied_reset_keeps_keyboard_controls_and_history(host,monkeypatch):
    window,provider,_,dry=host
    show_filled(window)
    before=snapshot(window)
    monkeypatch.setattr(QMessageBox,'question',lambda *_args,**_kwargs: QMessageBox.StandardButton.No)
    window.session_reset.click()
    window.task_timeline_jump_first_shortcut.activated.emit()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert snapshot(window)==before
    assert window.task_timeline_jump_first_shortcut.isEnabled()
    assert window.task_timeline_jump_latest_shortcut.isEnabled()
    assert provider.calls==0 and not dry.workers


def test_m159_composer_draft_and_existing_buttons_preserved(host):
    window,provider,_,dry=host
    bar=show_filled(window)
    window.input.setText('preservar envio')
    window.task_timeline_jump_latest.click()
    assert bar.value()==bar.maximum()
    window.task_timeline_jump_first_shortcut.activated.emit()
    assert bar.value()==bar.minimum()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert bar.value()==bar.maximum()
    assert window.input.text()=='preservar envio'
    assert provider.calls==0 and not dry.workers


@pytest.mark.parametrize('focus_name', ['input', 'transcript_find', 'chat', 'task_timeline_view'])
@pytest.mark.parametrize('key,to_max', [(FIRST,False), (LAST,True)])
def test_m159_recovery_real_key_from_four_focus_targets(host, focus_name, key, to_max):
    window, provider, _, dry = host
    bar = show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    widget = getattr(window, focus_name)
    bar.setValue(bar.maximum() // 2)
    before = snapshot(window)
    keyboard(window, key, widget)
    assert bar.maximum() > bar.minimum()
    assert bar.value() == (bar.maximum() if to_max else bar.minimum())
    assert snapshot(window) == before
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize('key,to_max', [(FIRST,False), (LAST,True)])
def test_m159_recovery_disabled_shortcut_does_not_take_editor_key(host, key, to_max):
    window, provider, _, dry = host
    bar = show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    shortcut = (window.task_timeline_jump_latest_shortcut if to_max
                else window.task_timeline_jump_first_shortcut)
    shortcut.setEnabled(False)
    try:
        keyboard(window, key)
        assert bar.value() == before
        assert provider.calls == 0 and not dry.workers
    finally:
        shortcut.setEnabled(True)


def test_m159_recovery_plain_home_end_does_not_trigger_timeline(host):
    window, provider, _, dry = host
    bar = show_filled(window)
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    window.input.setFocus()
    QTest.keyClick(window.input, Qt.Key.Key_Home)
    QTest.keyClick(window.input, Qt.Key.Key_End)
    QApplication.processEvents()
    assert bar.value() == before
    assert provider.calls == 0 and not dry.workers
