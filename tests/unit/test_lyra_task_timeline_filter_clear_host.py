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


def test_m155_control_identity_and_default(host):
    window, provider, _, dry = host
    button = window.task_timeline_filter_clear
    assert button.objectName() == "lyra_task_timeline_filter_clear"
    assert button.text() == "Limpar filtros"
    assert button.isEnabled()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_m155_clear_category_from_filtered_view(host, index):
    window, provider, memory, dry = host
    populate(window)
    before = snapshot(window)
    window.task_timeline_interruption_category.setCurrentIndex(index)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_filter_clear.click()
    assert not window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex() == 0
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window.task_timeline_visible_count.text() == "Na lista: 4/12 eventos recentes"
    assert snapshot(window) == before
    assert window._memory is memory and provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_m155_reset_category_even_when_filter_was_off(host, index):
    window, _, _, _ = host
    window.task_timeline_interruption_category.setCurrentIndex(index)
    assert not window.task_timeline_interruptions_only.isChecked()
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_interruption_category.currentIndex() == 0
    assert not window.task_timeline_interruptions_only.isChecked()


def test_m155_is_idempotent_and_preserves_events(host):
    window, _, _, _ = host
    populate(window)
    before = snapshot(window)
    window.task_timeline_filter_clear.click()
    window.task_timeline_filter_clear.click()
    assert snapshot(window) == before
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"


def test_m155_actual_qt_mouse_click(host):
    window, provider, _, dry = host
    populate(window)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_interruptions_only.setChecked(True)
    window.show()
    QApplication.processEvents()
    QTest.mouseClick(window.task_timeline_filter_clear, Qt.MouseButton.LeftButton)
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window.task_timeline_visible_count.text() == "Na lista: 4/12 eventos recentes"
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("disabled", ["button", "checkbox", "selector"])
def test_m155_disabled_controls_fail_closed(host, disabled):
    window, _, _, _ = host
    populate(window)
    selector = window.task_timeline_interruption_category
    checkbox = window.task_timeline_interruptions_only
    button = window.task_timeline_filter_clear
    selector.setCurrentIndex(3)
    checkbox.setChecked(True)
    before = (snapshot(window), selector.currentIndex(), checkbox.isChecked())
    widget = {"button": button, "checkbox": checkbox, "selector": selector}[disabled]
    widget.setEnabled(False)
    try:
        window._clear_task_timeline_filters()
        assert (snapshot(window), selector.currentIndex(), checkbox.isChecked()) == before
    finally:
        widget.setEnabled(True)


@pytest.mark.parametrize("corruption", ["label", "data", "extra", "removed"])
def test_m155_corrupted_selector_model_refused(host, corruption):
    window, provider, _, dry = host
    selector = window.task_timeline_interruption_category
    window.task_timeline_interruptions_only.setChecked(True)
    selector.setCurrentIndex(2)
    if corruption == "label":
        selector.setItemText(1, "UNTRUSTED")
    elif corruption == "data":
        selector.setItemData(1, "UNTRUSTED")
    elif corruption == "extra":
        selector.addItem("PRIVATE", "private")
    else:
        selector.removeItem(1)
    previous = (window.task_timeline_interruptions_only.isChecked(), selector.currentIndex())
    window._clear_task_timeline_filters()
    assert (window.task_timeline_interruptions_only.isChecked(), selector.currentIndex()) == previous
    assert provider.calls == 0 and not dry.workers


def test_m155_invalid_index_refused(host):
    window, _, _, _ = host
    selector = window.task_timeline_interruption_category
    window.task_timeline_interruptions_only.setChecked(True)
    selector.setCurrentIndex(-1)
    window._clear_task_timeline_filters()
    assert window.task_timeline_interruptions_only.isChecked()
    assert selector.currentIndex() == -1


def test_m155_does_not_open_hidden_history_panel(host):
    window, _, _, _ = host
    assert window.task_timeline_view.isHidden()
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_view.isHidden()


def test_m155_existing_shortcuts_remain_working(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · todas"


def test_m155_two_windows_isolation(host):
    first, _, _, _ = host
    second = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        populate(first)
        first.task_timeline_interruptions_only.setChecked(True)
        first.task_timeline_interruption_category.setCurrentIndex(3)
        second.task_timeline_interruptions_only.setChecked(True)
        second.task_timeline_interruption_category.setCurrentIndex(1)
        first.task_timeline_filter_clear.click()
        assert first.task_timeline_view_scope.text() == "Visão: histórico completo"
        assert second.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"
        assert len(first._task_timeline.snapshot()) == 4
        assert not second._task_timeline.snapshot()
    finally:
        second.close()


def test_m155_busy_dry_worker_does_not_dispatch(host):
    window, provider, memory, dry = host
    populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window._set_busy(True)
    try:
        window._clear_task_timeline_filters()
        assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
        assert window._memory is memory and provider.calls == 0 and not dry.workers
    finally:
        window._set_busy(False)


def test_m155_denied_session_reset_does_not_erase_history(host, monkeypatch):
    window, _, _, _ = host
    populate(window)
    before = snapshot(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    window.task_timeline_filter_clear.click()
    assert snapshot(window) == before


def test_m155_accepted_session_reset_keeps_clear_button(host, monkeypatch):
    window, provider, memory, dry = host
    populate(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert not window._task_timeline.snapshot()
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window._memory is memory and provider.calls == 0 and not dry.workers
