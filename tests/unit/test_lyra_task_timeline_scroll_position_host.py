from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

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
    for index in range(12):
        message, terminal = (
            (START, False), (PENDING, False),
            (CANCELLED, True), (FAILED, True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=message, terminal=terminal)
        )
    window._refresh_task_timeline()


def show_scrollable(window):
    populate(window)
    window.show()
    QApplication.processEvents()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    return bar


def position(window):
    return window.task_timeline_scroll_position.text()


def snapshot(window):
    model = window._task_timeline
    return (
        model.snapshot(), model.summary(),
        model.interruption_count_label(),
        model.interruption_breakdown_label(),
    )


def no_effect(window, provider, memory, dry, before):
    assert snapshot(window) == before
    assert window._memory is memory
    assert provider.calls == 0
    assert not dry.workers
    assert window.task_timeline_view.isReadOnly()


def test_m162_default_label_identity_and_no_scroll(host):
    window, provider, memory, dry = host
    label = window.task_timeline_scroll_position
    assert isinstance(label, QLabel)
    assert label.objectName() == "lyra_task_timeline_scroll_position"
    assert label.isEnabled() and not label.isHidden()
    assert position(window) == "Posição: sem rolagem"
    assert "eventos" in label.toolTip()
    no_effect(window, provider, memory, dry, snapshot(window))


@pytest.mark.parametrize("value,minimum,maximum,expected", [
    (0, 0, 0, "Posição: sem rolagem"),
    (7, 7, 7, "Posição: sem rolagem"),
    (0, 0, 10, "Posição: início"),
    (3, 0, 10, "Posição: intermediária"),
    (9, 0, 10, "Posição: intermediária"),
    (10, 0, 10, "Posição: fim"),
    (-3, -3, 2, "Posição: início"),
    (2, -3, 2, "Posição: fim"),
    (-1, 0, 10, "Posição: indisponível"),
    (11, 0, 10, "Posição: indisponível"),
    (5, 10, 0, "Posição: indisponível"),
    (True, 0, 10, "Posição: indisponível"),
    (5, False, 10, "Posição: indisponível"),
    (5, 0, True, "Posição: indisponível"),
    ("RAW_SECRET", 0, 10, "Posição: indisponível"),
    (5.0, 0, 10, "Posição: indisponível"),
])
def test_m162_finite_helper_rejects_invalid_inputs(host, value, minimum, maximum, expected):
    window, provider, memory, dry = host
    assert window._task_timeline_scroll_position_text(value, minimum, maximum) == expected
    no_effect(window, provider, memory, dry, snapshot(window))


@pytest.mark.parametrize("where,expected", [
    ("start", "Posição: início"),
    ("middle", "Posição: intermediária"),
    ("end", "Posição: fim"),
])
def test_m162_real_scrollbar_value_signal_updates_label(host, where, expected):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    before = snapshot(window)
    value = (
        bar.minimum() if where == "start" else
        bar.maximum() if where == "end" else
        (bar.minimum() + bar.maximum()) // 2
    )
    assert where != "middle" or bar.maximum() - bar.minimum() > 1
    bar.setValue(value)
    QApplication.processEvents()
    assert position(window) == expected
    no_effect(window, provider, memory, dry, before)


@pytest.mark.parametrize("action,expected", [
    ("first", "Posição: início"),
    ("latest", "Posição: fim"),
])
def test_m162_first_latest_controls_refresh(host, action, expected):
    window, provider, memory, dry = host
    show_scrollable(window)
    before = snapshot(window)
    button = (
        window.task_timeline_jump_first if action == "first"
        else window.task_timeline_jump_latest
    )
    button.click()
    QApplication.processEvents()
    assert position(window) == expected
    no_effect(window, provider, memory, dry, before)


@pytest.mark.parametrize("direction,expected", [
    (-1, "Posição: início"),
    (1, "Posição: fim"),
])
def test_m162_page_buttons_update_position_at_bounds(host, direction, expected):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    before = snapshot(window)
    bar.setValue(bar.minimum() if direction == -1 else bar.maximum())
    button = (
        window.task_timeline_page_previous if direction == -1
        else window.task_timeline_page_next
    )
    button.click()
    QApplication.processEvents()
    assert position(window) == expected
    no_effect(window, provider, memory, dry, before)


@pytest.mark.parametrize("key,expected", [
    (Qt.Key.Key_Home, "Posição: início"),
    (Qt.Key.Key_End, "Posição: fim"),
])
def test_m162_existing_first_latest_keyboard_shortcuts_update_position(host, key, expected):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    before = snapshot(window)
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    window.activateWindow()
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        window.input, key,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert position(window) == expected
    no_effect(window, provider, memory, dry, before)


@pytest.mark.parametrize("key,direction", [
    (Qt.Key.Key_PageUp, -1),
    (Qt.Key.Key_PageDown, 1),
])
def test_m162_existing_paging_keyboard_shortcuts_update_position(host, key, direction):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    before = snapshot(window)
    start = bar.maximum() if direction == -1 else bar.minimum()
    bar.setValue(start)
    expected = max(
        bar.minimum(), min(bar.maximum(), start + direction * max(1, bar.pageStep()))
    )
    window.activateWindow()
    window.input.setFocus()
    QApplication.processEvents()
    QTest.keyClick(
        window.input, key,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert bar.value() == expected
    assert position(window) == window._task_timeline_scroll_position_text(
        expected, bar.minimum(), bar.maximum()
    )
    no_effect(window, provider, memory, dry, before)


@pytest.mark.parametrize("category", [0, 1, 2, 3])
def test_m162_filter_categories_preserve_model_and_derive_viewport(host, category):
    window, provider, memory, dry = host
    show_scrollable(window)
    before = snapshot(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert position(window) == window._task_timeline_scroll_position_text(
        bar.value(), bar.minimum(), bar.maximum()
    )
    assert position(window) in (
        "Posição: sem rolagem", "Posição: início",
        "Posição: intermediária", "Posição: fim",
    )
    no_effect(window, provider, memory, dry, before)


def test_m162_malformed_filter_does_not_leak_selector_data(host):
    window, provider, memory, dry = host
    show_scrollable(window)
    before = snapshot(window)
    window.task_timeline_interruption_category.setItemData(0, "RAW_SECRET")
    window.task_timeline_interruptions_only.setChecked(True)
    window._refresh_task_timeline()
    QApplication.processEvents()
    assert "RAW_SECRET" not in position(window)
    assert "RAW_SECRET" not in window.task_timeline_view.toPlainText()
    no_effect(window, provider, memory, dry, before)


def test_m162_two_window_scrollbars_and_indicators_independent(host):
    window, provider, memory, dry = host
    other = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        left = show_scrollable(window)
        right = show_scrollable(other)
        left.setValue(left.minimum())
        right.setValue(right.maximum())
        QApplication.processEvents()
        assert position(window) == "Posição: início"
        assert position(other) == "Posição: fim"
        left.setValue(left.maximum())
        assert position(window) == "Posição: fim"
        assert position(other) == "Posição: fim"
        right.setValue(right.minimum())
        assert position(other) == "Posição: início"
        assert position(window) == "Posição: fim"
        no_effect(window, provider, memory, dry, snapshot(window))
    finally:
        other.close()


def test_m162_busy_dry_task_updates_only_presentation(host):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    window._start_tool_task("simulação", ())
    assert not window.input.isEnabled() and len(dry.workers) == 1
    populate(window)
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    before = snapshot(window)
    bar.setValue(bar.minimum())
    assert position(window) == "Posição: início"
    bar.setValue(bar.maximum())
    assert position(window) == "Posição: fim"
    assert snapshot(window) == before
    assert window._memory is memory
    assert provider.calls == 0 and len(dry.workers) == 1


@pytest.mark.parametrize("accepted", [False, True])
def test_m162_reset_recomputes_and_keeps_label(host, monkeypatch, accepted):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    bar.setValue(bar.maximum())
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
    assert position(window) == window._task_timeline_scroll_position_text(
        bar.value(), bar.minimum(), bar.maximum()
    )
    assert window.task_timeline_scroll_position.isEnabled()
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers


def test_m162_visibility_toggle_preserves_read_only_label(host):
    window, provider, memory, dry = host
    bar = show_scrollable(window)
    before = snapshot(window)
    bar.setValue(bar.maximum())
    assert position(window) == "Posição: fim"
    window.task_timeline_toggle.click()
    assert window.task_timeline_view.isHidden()
    assert position(window) == window._task_timeline_scroll_position_text(
        bar.value(), bar.minimum(), bar.maximum()
    )
    window.task_timeline_toggle.click()
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    assert position(window) == window._task_timeline_scroll_position_text(
        bar.value(), bar.minimum(), bar.maximum()
    )
    no_effect(window, provider, memory, dry, before)
