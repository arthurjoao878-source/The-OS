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


def test_m158_button_identity_tooltip_and_default(host):
    window, provider, _, dry = host
    button = window.task_timeline_jump_first
    assert button.objectName() == "lyra_task_timeline_jump_first"
    assert button.text() == "Primeiro evento"
    assert button.isEnabled()
    assert "lista visível" in button.toolTip()
    assert window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0 and not dry.workers


def test_m158_real_qt_mouse_click_reveals_hidden_panel(host):
    window, provider, memory, dry = host
    populate_twelve(window)
    before = snapshot(window)
    window.show()
    QApplication.processEvents()
    assert window.task_timeline_view.isHidden()
    QTest.mouseClick(window.task_timeline_jump_first, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.isReadOnly()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.minimum()
    assert snapshot(window) == before
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m158_existing_visible_panel_scrolls_to_first(host):
    window, provider, _, dry = host
    populate_twelve(window)
    window.show()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    window.task_timeline_jump_first.click()
    assert bar.value() == bar.minimum()
    assert provider.calls == 0 and not dry.workers


@pytest.mark.parametrize("category", [0, 1, 2, 3])
def test_m158_preserves_filter_category_and_labels(host, category):
    window, provider, _, dry = host
    populate_twelve(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    window.task_timeline_interruptions_only.setChecked(True)
    before = snapshot(window)
    visible_before = window.task_timeline_view.toPlainText()
    count_before = window.task_timeline_visible_count.text()
    scope_before = window.task_timeline_view_scope.text()
    window.task_timeline_jump_first.click()
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex() == category
    assert window.task_timeline_view.toPlainText() == visible_before
    assert window.task_timeline_visible_count.text() == count_before
    assert window.task_timeline_view_scope.text() == scope_before
    assert snapshot(window) == before
    assert provider.calls == 0 and not dry.workers


def test_m158_empty_history_navigation_safe(host):
    window, provider, _, dry = host
    assert not window._task_timeline.snapshot()
    before = window.task_timeline_view.toPlainText()
    window.task_timeline_jump_first.click()
    assert not window.task_timeline_view.isHidden()
    assert window.task_timeline_view.toPlainText() == before
    assert not window._task_timeline.snapshot()
    assert provider.calls == 0 and not dry.workers


def test_m158_idempotent_multiple_clicks(host):
    window, _, _, _ = host
    populate_twelve(window)
    old = snapshot(window)
    for _ in range(3):
        window.task_timeline_jump_first.click()
    assert snapshot(window) == old
    assert window.task_timeline_view.isReadOnly()
    assert not window.task_timeline_view.isHidden()


@pytest.mark.parametrize("disabled", ["button", "timeline"])
def test_m158_disabled_control_fails_closed(host, disabled):
    window, provider, _, dry = host
    populate_twelve(window)
    control = (
        window.task_timeline_jump_first if disabled == "button"
        else window.task_timeline_view
    )
    control.setEnabled(False)
    before = snapshot(window)
    try:
        window._jump_to_first_task_timeline_event()
        window.task_timeline_jump_first.click()
        assert window.task_timeline_view.isHidden()
        assert snapshot(window) == before
        assert provider.calls == 0 and not dry.workers
    finally:
        control.setEnabled(True)


def test_m158_does_not_mutate_draft_find_follow_or_personality(host):
    window, provider, memory, dry = host
    populate_twelve(window)
    window.input.setText("rascunho reservado")
    window.transcript_find.setText("busca reservada")
    window.chat_follow.setChecked(False)
    window.personality_tone.setCurrentIndex(1)
    before = snapshot(window)
    window.task_timeline_jump_first.click()
    assert window.input.text() == "rascunho reservado"
    assert window.transcript_find.text() == "busca reservada"
    assert not window.chat_follow.isChecked()
    assert window.personality_tone.currentIndex() == 1
    assert snapshot(window) == before
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m158_invalid_category_never_leaks_raw_history(host):
    window, provider, _, dry = host
    populate_twelve(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setItemData(1, "private-raw")
    window.task_timeline_interruption_category.setCurrentIndex(1)
    before = window.task_timeline_view.toPlainText()
    assert "private-raw" not in before
    window.task_timeline_jump_first.click()
    assert window.task_timeline_view.toPlainText() == before
    assert "private-raw" not in window.task_timeline_view.toPlainText()
    assert provider.calls == 0 and not dry.workers


def test_m158_two_window_viewport_isolation(host):
    first, _, _, _ = host
    second = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        populate_twelve(first)
        populate_twelve(second)
        first.task_timeline_jump_first.click()
        assert not first.task_timeline_view.isHidden()
        assert second.task_timeline_view.isHidden()
        assert second._task_timeline.snapshot() == first._task_timeline.snapshot()
    finally:
        second.close()


def test_m158_busy_view_only_no_dispatch(host):
    window, provider, memory, dry = host
    populate_twelve(window)
    before = snapshot(window)
    window._set_busy(True)
    try:
        window.task_timeline_jump_first.click()
        assert not window.task_timeline_view.isHidden()
        assert snapshot(window) == before
        assert window._memory is memory and provider.calls == 0 and not dry.workers
    finally:
        window._set_busy(False)


def test_m158_denied_reset_preserves_history_and_navigation(host, monkeypatch):
    window, _, _, _ = host
    populate_twelve(window)
    before = snapshot(window)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    window.task_timeline_jump_first.click()
    assert snapshot(window) == before
    assert not window.task_timeline_view.isHidden()


def test_m158_accepted_reset_keeps_navigation(host, monkeypatch):
    window, provider, memory, dry = host
    populate_twelve(window)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert not window._task_timeline.snapshot()
    window.task_timeline_jump_first.click()
    assert window.task_timeline_view.isReadOnly()
    assert not window.task_timeline_view.isHidden()
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m158_existing_clear_button_and_shortcut_unchanged(host):
    window, _, _, _ = host
    populate_twelve(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    window.task_timeline_jump_first.click()
    assert window.task_timeline_interruption_category.currentIndex() == 3
    window.task_timeline_filter_clear_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_filter_clear.click()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"



def test_m158_complements_m157_latest_navigation_with_real_qt_click(host):
    window, provider, _, dry = host
    populate_twelve(window)
    window.show()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    QTest.mouseClick(window.task_timeline_jump_latest, Qt.MouseButton.LeftButton)
    assert bar.value() == bar.maximum()
    QTest.mouseClick(window.task_timeline_jump_first, Qt.MouseButton.LeftButton)
    assert bar.value() == bar.minimum()
    QTest.mouseClick(window.task_timeline_jump_latest, Qt.MouseButton.LeftButton)
    assert bar.value() == bar.maximum()
    assert window._task_timeline.snapshot()
    assert provider.calls == 0 and not dry.workers


def test_m158_cannot_navigate_disabled_timeline_at_existing_scroll_position(host):
    window, provider, _, dry = host
    populate_twelve(window)
    window.show()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    bar.setValue(bar.maximum())
    window.task_timeline_view.setEnabled(False)
    try:
        window._jump_to_first_task_timeline_event()
        window.task_timeline_jump_first.click()
        assert bar.value() == bar.maximum()
        assert provider.calls == 0 and not dry.workers
    finally:
        window.task_timeline_view.setEnabled(True)
