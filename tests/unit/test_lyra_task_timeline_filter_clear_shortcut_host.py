from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
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


def test_m156_shortcut_identity_scope_and_tooltip(host):
    window, provider, _, dry = host
    shortcut = window.task_timeline_filter_clear_shortcut
    assert shortcut.objectName() == "lyra_task_timeline_filter_clear_shortcut"
    assert shortcut.key().toString() == "Ctrl+Shift+U"
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.isEnabled()
    assert "Ctrl+Shift+U" in window.task_timeline_filter_clear.toolTip()
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_m156_shortcut_signal_restores_all_categories(host, index):
    window, provider, memory, dry = host
    populate(window)
    old = snapshot(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(index)
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex() == 0
    assert window.task_timeline_visible_count.text() == "Na lista: 4/12 eventos recentes"
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert snapshot(window) == old
    assert window._memory is memory and provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_m156_shortcut_resets_inert_category_when_filter_off(host, index):
    window, _, _, _ = host
    window.task_timeline_interruption_category.setCurrentIndex(index)
    assert not window.task_timeline_interruptions_only.isChecked()
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_interruption_category.currentIndex() == 0
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m156_real_qt_composer_keyboard_shortcut(host):
    window, provider, _, dry = host
    populate(window)
    old = snapshot(window)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    window.show()
    QApplication.processEvents()
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(window.input, Qt.Key.Key_U,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QApplication.processEvents()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert snapshot(window) == old and provider.calls == 0 and not dry.workers


def test_m156_real_qt_transcript_keyboard_shortcut(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.show()
    QApplication.processEvents()
    window.chat.setFocus()
    QTest.keyClick(window.chat, Qt.Key.Key_U,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QApplication.processEvents()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window.chat.isReadOnly()


def test_m156_real_qt_find_keyboard_shortcut_preserves_find(host):
    window, _, _, _ = host
    window.transcript_find.setText("evidence")
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    window.show()
    QApplication.processEvents()
    window.transcript_find.setFocus()
    QTest.keyClick(window.transcript_find, Qt.Key.Key_U,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QApplication.processEvents()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window.transcript_find.text() == "evidence"


@pytest.mark.parametrize("disabled", ["shortcut", "button", "checkbox", "selector"])
def test_m156_disabled_controls_fail_closed(host, disabled):
    window, _, _, _ = host
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    controls = {
        "shortcut": window.task_timeline_filter_clear_shortcut,
        "button": window.task_timeline_filter_clear,
        "checkbox": window.task_timeline_interruptions_only,
        "selector": window.task_timeline_interruption_category,
    }
    old = (window.task_timeline_interruption_category.currentIndex(),
           window.task_timeline_interruptions_only.isChecked())
    controls[disabled].setEnabled(False)
    try:
        window._clear_task_timeline_filters_shortcut()
        assert old == (window.task_timeline_interruption_category.currentIndex(),
                       window.task_timeline_interruptions_only.isChecked())
    finally:
        controls[disabled].setEnabled(True)


@pytest.mark.parametrize("corruption", ["label", "data", "extra", "removed"])
def test_m156_corrupted_selector_refused(host, corruption):
    window, provider, _, dry = host
    selector = window.task_timeline_interruption_category
    selector.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    if corruption == "label":
        selector.setItemText(1, "PRIVATE")
    elif corruption == "data":
        selector.setItemData(1, "private")
    elif corruption == "extra":
        selector.addItem("Private", "private")
    else:
        selector.removeItem(1)
    old = (window.task_timeline_interruptions_only.isChecked(), selector.currentIndex())
    window._clear_task_timeline_filters_shortcut()
    assert old == (window.task_timeline_interruptions_only.isChecked(), selector.currentIndex())
    assert provider.calls == 0 and not dry.workers


def test_m156_invalid_selector_index_fails_closed(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(-1)
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex() == -1


def test_m156_button_and_keyboard_share_handler(host):
    window, _, _, _ = host
    populate(window)
    old = snapshot(window)
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert snapshot(window) == old


def test_m156_key_signal_idempotent_does_not_toggle_panel(host):
    window, _, _, _ = host
    assert window.task_timeline_view.isHidden()
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_filter_clear_shortcut.activated.emit()
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"


def test_m156_existing_shortcuts_unchanged(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"
    window.task_timeline_toggle_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_visible_count.text().endswith("/12 eventos recentes")


def test_m156_two_qt_windows_isolation(host):
    first, _, _, _ = host
    second = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        first.task_timeline_interruption_category.setCurrentIndex(3)
        first.task_timeline_interruptions_only.setChecked(True)
        second.task_timeline_interruption_category.setCurrentIndex(2)
        second.task_timeline_interruptions_only.setChecked(True)
        first.task_timeline_filter_clear_shortcut.activated.emit()
        assert first.task_timeline_view_scope.text() == "Visão: histórico completo"
        assert second.task_timeline_view_scope.text() == "Visão: interrupções · canceladas"
    finally:
        second.close()


def test_m156_busy_shortcut_no_task_dispatch(host):
    window, provider, memory, dry = host
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    window._set_busy(True)
    try:
        window.task_timeline_filter_clear_shortcut.activated.emit()
        assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
        assert window._memory is memory and provider.calls == 0 and not dry.workers
    finally:
        window._set_busy(False)


def test_m156_denied_session_reset_keeps_filters_shortcut(host, monkeypatch):
    window, _, _, _ = host
    populate(window)
    old = snapshot(window)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert snapshot(window) == old
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"


def test_m156_accepted_session_reset_shortcut_remains(host, monkeypatch):
    window, provider, memory, dry = host
    populate(window)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    window.task_timeline_interruptions_only.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert not window._task_timeline.snapshot()
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window._memory is memory and provider.calls == 0 and not dry.workers
