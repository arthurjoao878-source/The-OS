from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QSlider

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
        raise AssertionError("continuation forbidden")

    def reply(self, text, *, history=()):
        raise AssertionError("reply forbidden")


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
        text, terminal = (
            ("Tarefa: iniciada · 0/4 etapas", False),
            ("Tarefa: cancelamento solicitado · aguardando confirmação", False),
            ("Tarefa: cancelada · 0/4 etapas", True),
            ("Tarefa: falhou · 1/4 etapas · sistema", True),
        )[index % 4]
        assert window._task_timeline.record(
            HostWorkflowProgressView(text=text, terminal=terminal)
        )
    window._refresh_task_timeline()


def show_history(window):
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
        window.input.text(), window.transcript_find.text(),
        window.chat.toPlainText(), window.chat_follow.isChecked(),
    )


def passive(window, provider, memory, dry, before, workers=0):
    assert snapshot(window) == before
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()
    assert provider.calls == 0
    assert len(dry.workers) == workers


def scroll_percent(window):
    bar = window.task_timeline_view.verticalScrollBar()
    span = bar.maximum() - bar.minimum()
    if span <= 0:
        return 0
    return (100 * (bar.value() - bar.minimum()) + span // 2) // span


def check_sync(window):
    assert window.task_timeline_seek_percent.value() == scroll_percent(window)
    bar = window.task_timeline_view.verticalScrollBar()
    assert window.task_timeline_scroll_position.text() == (
        window._task_timeline_scroll_position_text(
            bar.value(), bar.minimum(), bar.maximum()
        )
    )


def test_m166_widget_identity_range_and_initial_state(host):
    window, provider, memory, dry = host
    slider = window.task_timeline_seek_percent
    assert isinstance(slider, QSlider)
    assert slider.objectName() == "lyra_task_timeline_seek_percent"
    assert slider.orientation() == Qt.Orientation.Horizontal
    assert slider.minimum() == 0 and slider.maximum() == 100
    assert slider.value() == 0 and slider.isEnabled()
    assert slider.accessibleName() and slider.toolTip()
    assert window.task_timeline_view.isReadOnly()
    before = snapshot(window)
    passive(window, provider, memory, dry, before)


def test_m166_empty_timeline_zero_range_is_safe(host):
    window, provider, memory, dry = host
    window.show()
    QApplication.processEvents()
    before = snapshot(window)
    window.task_timeline_seek_percent.setValue(50)
    QApplication.processEvents()
    assert not window.task_timeline_view.isHidden()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() == bar.minimum()
    assert bar.value() == bar.minimum()
    check_sync(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("percent", (0, 10, 25, 50, 75, 90, 100))
def test_m166_bounded_direct_seek_uses_real_scrollbar(host, percent):
    window, provider, memory, dry = host
    bar = show_history(window)
    before = snapshot(window)
    window.task_timeline_seek_percent.setValue(percent)
    QApplication.processEvents()
    expected = bar.minimum() + ((bar.maximum() - bar.minimum()) * percent + 50) // 100
    assert bar.value() == expected
    check_sync(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("origin", ("start", "middle", "end"))
def test_m166_external_scrollbar_changes_sync_slider(host, origin):
    window, provider, memory, dry = host
    bar = show_history(window)
    before = snapshot(window)
    target = {"start": bar.minimum(), "middle": (bar.minimum() + bar.maximum()) // 2,
              "end": bar.maximum()}[origin]
    bar.setValue(target)
    QApplication.processEvents()
    check_sync(window)
    passive(window, provider, memory, dry, before)


def test_m166_original_navigation_buttons_sync_slider(host):
    window, provider, memory, dry = host
    bar = show_history(window)
    before = snapshot(window)
    window.task_timeline_jump_first.click()
    assert bar.value() == bar.minimum()
    check_sync(window)
    window.task_timeline_jump_latest.click()
    assert bar.value() == bar.maximum()
    check_sync(window)
    window.task_timeline_jump_middle.click()
    check_sync(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("category", ("all", "pending", "cancelled", "failed"))
def test_m166_filters_recompute_from_qt_range(host, category):
    window, provider, memory, dry = host
    show_history(window)
    selector = window.task_timeline_interruption_category
    idx = selector.findData(category)
    assert idx >= 0
    selector.setCurrentIndex(idx)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    before = snapshot(window)
    check_sync(window)
    window.task_timeline_seek_percent.setValue(75)
    QApplication.processEvents()
    check_sync(window)
    window.task_timeline_interruptions_only.setChecked(False)
    QApplication.processEvents()
    check_sync(window)
    assert window._task_timeline.snapshot() == before[0]
    assert window.input.text() == before[7]
    assert window.transcript_find.text() == before[8]
    assert window.chat.toPlainText() == before[9]
    assert window.chat_follow.isChecked() == before[10]
    assert provider.calls == 0 and not dry.workers
    assert window._memory is memory


@pytest.mark.parametrize("invalid", (-1, 101, True, False, "50", 50.0, None))
def test_m166_malformed_direct_handler_rejected(host, invalid):
    window, provider, memory, dry = host
    bar = show_history(window)
    bar.setValue(bar.maximum())
    before = snapshot(window)
    old = bar.value()
    window._seek_task_timeline_percentage(invalid)
    assert bar.value() == old
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("disabled", ("slider", "timeline"))
def test_m166_disabled_controls_fail_closed(host, disabled):
    window, provider, memory, dry = host
    bar = show_history(window)
    bar.setValue(bar.minimum())
    before = snapshot(window)
    control = window.task_timeline_seek_percent if disabled == "slider" else window.task_timeline_view
    control.setEnabled(False)
    try:
        window._seek_task_timeline_percentage(100)
        assert bar.value() == bar.minimum()
        if disabled == "slider":
            window.task_timeline_seek_percent.setValue(100)
            assert bar.value() == bar.minimum()
    finally:
        control.setEnabled(True)
    passive(window, provider, memory, dry, before)


def test_m166_keyboard_slider_navigation_uses_same_handler(host):
    window, provider, memory, dry = host
    bar = show_history(window)
    before = snapshot(window)
    slider = window.task_timeline_seek_percent
    slider.setValue(0)
    slider.setFocus()
    QApplication.processEvents()
    QTest.keyClick(slider, Qt.Key.Key_Right)
    QApplication.processEvents()
    assert bar.value() >= bar.minimum()
    assert bar.value() <= bar.maximum()
    check_sync(window)
    passive(window, provider, memory, dry, before)


def test_m166_two_window_slider_isolation(host):
    window, provider, memory, dry = host
    second_provider = ControlledProvider()
    other = MainWindow(ActionRegistry(), object(), second_provider, build_default_tool_catalog())
    try:
        bar = show_history(window)
        otherbar = show_history(other)
        before = snapshot(window)
        other_before = snapshot(other)
        otherbar.setValue(otherbar.minimum())
        bar.setValue(bar.minimum())
        window.task_timeline_seek_percent.setValue(100)
        QApplication.processEvents()
        assert bar.value() == bar.maximum()
        assert otherbar.value() == otherbar.minimum()
        assert snapshot(other) == other_before
        other.task_timeline_seek_percent.setValue(50)
        QApplication.processEvents()
        assert bar.value() == bar.maximum()
        check_sync(window)
        check_sync(other)
        passive(window, provider, memory, dry, before)
        assert second_provider.calls == 0
    finally:
        other.close()


def test_m166_busy_dry_task_slider_is_presentation_only(host):
    window, provider, memory, dry = host
    show_history(window)
    window._start_tool_task("simulação", ())
    assert len(dry.workers) == 1
    before = snapshot(window)
    window.task_timeline_seek_percent.setValue(100)
    QApplication.processEvents()
    check_sync(window)
    passive(window, provider, memory, dry, before, workers=1)


@pytest.mark.parametrize("accepted", (False, True))
def test_m166_reset_keeps_slider_operational(host, monkeypatch, accepted):
    window, provider, memory, dry = host
    show_history(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: (
        QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No
    ))
    window.session_reset.click()
    QApplication.processEvents()
    if accepted:
        assert window._task_timeline.snapshot() == ()
    else:
        assert len(window._task_timeline.snapshot()) > 0
    before = snapshot(window)
    window.task_timeline_seek_percent.setValue(100)
    QApplication.processEvents()
    check_sync(window)
    passive(window, provider, memory, dry, before)


def test_m166_repeated_seek_idempotent(host):
    window, provider, memory, dry = host
    bar = show_history(window)
    before = snapshot(window)
    slider = window.task_timeline_seek_percent
    for _ in range(16):
        slider.setValue(75)
        window._seek_task_timeline_percentage(75)
        check_sync(window)
    assert bar.minimum() <= bar.value() <= bar.maximum()
    passive(window, provider, memory, dry, before)
