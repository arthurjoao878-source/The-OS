from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TASK_TIMELINE_LIMIT, TaskTimeline
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

START = "Tarefa: iniciada · 0/4 etapas"
PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"
DIRECT_FAILURE = "Ação direta: falha reportada · open_application"
SUCCESS = "Ação direta: pós-condição verificada · open_application"


class ControlledProvider:
    provider_id = "fake"

    def __init__(self) -> None:
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
    def __init__(self) -> None:
        self.workers: list[object] = []

    def start(self, worker) -> None:
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


def _view(text: str, terminal: bool) -> HostWorkflowProgressView:
    return HostWorkflowProgressView(text=text, terminal=terminal)


def _populate(timeline: TaskTimeline) -> None:
    for text, terminal in (
        (START, False), (PENDING, False), (CANCELLED, True),
        (FAILED, True), (SUCCESS, True),
    ):
        assert timeline.record(_view(text, terminal))


def _label(count: int) -> str:
    return f"Na lista: {count}/{TASK_TIMELINE_LIMIT} eventos recentes"


@pytest.mark.parametrize("filter_enabled,category", [
    (False, "all"), (False, "pending"), (False, "INVALID"),
    (True, "all"), (True, "pending"), (True, "cancelled"), (True, "failed"),
])
def test_m153_empty_view_is_zero(filter_enabled, category):
    assert TaskTimeline().visible_entry_count_label(
        interruptions_only=filter_enabled, category=category
    ) == _label(0)


def test_m153_full_view_counts_all_events_not_only_interruptions():
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.visible_entry_count_label(
        interruptions_only=False, category="failed"
    ) == _label(5)
    assert timeline.interruption_count_label() == "Interrupções: 3/12 eventos recentes"


@pytest.mark.parametrize("category,expected", [
    ("all", 3), ("pending", 1), ("cancelled", 1), ("failed", 1),
])
def test_m153_filtered_count_reuses_safe_category_view(category, expected):
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category=category
    ) == _label(expected)
    assert timeline.display_interruption_category(category).count(". ") == expected


@pytest.mark.parametrize("category", [None, 7, True, "unknown", "", "PENDING"])
def test_m153_unknown_filtered_category_fails_closed(category):
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category=category  # type: ignore[arg-type]
    ) == _label(0)


@pytest.mark.parametrize("flag", [None, 1, "yes", [], 0])
def test_m153_invalid_boolean_fails_closed(flag):
    timeline = TaskTimeline()
    _populate(timeline)
    assert timeline.visible_entry_count_label(
        interruptions_only=flag, category="all"  # type: ignore[arg-type]
    ) == _label(0)


def test_m153_rejects_fake_interruption_label_in_filtered_count():
    timeline = TaskTimeline()
    assert timeline.record(_view("Tarefa: falhou · PRIVATE_PATH", True))
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category="failed"
    ) == _label(0)
    assert timeline.visible_entry_count_label(
        interruptions_only=False, category="failed"
    ) == _label(1)


def test_m153_repeated_record_does_not_inflate_count():
    timeline = TaskTimeline()
    assert timeline.record(_view(PENDING, False))
    assert not timeline.record(_view(PENDING, False))
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category="pending"
    ) == _label(1)


def test_m153_terminal_upgrade_reclassifies_existing_entry():
    timeline = TaskTimeline()
    assert timeline.record(_view(PENDING, False))
    assert timeline.record(_view(PENDING, True))
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category="pending"
    ) == _label(0)
    assert timeline.visible_entry_count_label(
        interruptions_only=False, category="all"
    ) == _label(1)


def test_m153_rolling_window_never_exceeds_twelve():
    timeline = TaskTimeline()
    _populate(timeline)
    for index in range(20):
        assert timeline.record(_view(f"Ação direta: falha reportada · action_{index}", True))
    assert len(timeline.snapshot()) == TASK_TIMELINE_LIMIT
    assert timeline.visible_entry_count_label(
        interruptions_only=False, category="all"
    ) == _label(12)
    assert timeline.visible_entry_count_label(
        interruptions_only=True, category="failed"
    ) == _label(12)


def test_m153_read_only_count_does_not_mutate_existing_state():
    timeline = TaskTimeline()
    _populate(timeline)
    original = (timeline.snapshot(), timeline.summary(), timeline.interruption_breakdown_label())
    for _ in range(4):
        for category in ("all", "pending", "cancelled", "failed"):
            timeline.visible_entry_count_label(interruptions_only=True, category=category)
    assert original == (
        timeline.snapshot(), timeline.summary(), timeline.interruption_breakdown_label()
    )


def test_m153_clear_resets_count():
    timeline = TaskTimeline()
    _populate(timeline)
    timeline.clear()
    assert timeline.visible_entry_count_label(
        interruptions_only=False, category="all"
    ) == _label(0)


def test_m153_qt_default_widget_and_panel_hidden(host):
    window, provider, _, dry = host
    label = window.task_timeline_visible_count
    assert label.objectName() == "lyra_task_timeline_visible_count"
    assert label.text() == _label(0)
    assert not label.isHidden()
    assert window.task_timeline_view.isHidden()
    assert provider.calls == 0 and not dry.workers


def test_m153_qt_refresh_full_and_filtered_views(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    assert window.task_timeline_visible_count.text() == _label(5)
    window.task_timeline_interruptions_only.setChecked(True)
    assert window.task_timeline_visible_count.text() == _label(3)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    assert window.task_timeline_visible_count.text() == _label(1)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    assert window.task_timeline_visible_count.text() == _label(1)


def test_m153_qt_shortcut_roundtrip_respects_existing_category(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
    assert window.task_timeline_visible_count.text() == _label(5)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_visible_count.text() == _label(1)
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_visible_count.text() == _label(5)


def test_m153_qt_panel_toggle_does_not_change_count(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    for _ in range(2):
        window.task_timeline_toggle_shortcut.activated.emit()
        assert window.task_timeline_visible_count.text() == _label(5)


def test_m153_qt_invalid_category_is_zero_only_when_filtered(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    combo = window.task_timeline_interruption_category
    combo.setItemData(0, "PRIVADO")
    assert window.task_timeline_visible_count.text() == _label(5)
    window.task_timeline_interruptions_only.setChecked(True)
    assert window.task_timeline_visible_count.text() == _label(0)
    assert "PRIVADO" not in window.task_timeline_view.toPlainText()


def test_m153_qt_denied_reset_preserves_count(host, monkeypatch):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No
    )
    window.session_reset.click()
    assert window.task_timeline_visible_count.text() == _label(5)


def test_m153_qt_accepted_reset_clears_count_preserves_selection(host, monkeypatch):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )
    window.session_reset.click()
    assert window.task_timeline_visible_count.text() == _label(0)
    assert window.task_timeline_interruption_category.currentData() == "failed"
    assert window._memory is memory and provider.calls == 0 and not dry.workers


def test_m153_qt_new_task_clears_view_count_without_dispatch(host):
    window, provider, _, dry = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window._start_tool_task("controlled", ())
    assert window.task_timeline_visible_count.text() == _label(0)
    assert provider.calls == 0 and len(dry.workers) == 1
    window._active_control = None
    window._set_busy(False)


def test_m153_qt_busy_filter_remains_passive(host):
    window, provider, memory, dry = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window._set_busy(True)
    try:
        window.task_timeline_interruptions_only.setChecked(True)
        window.task_timeline_interruption_category.setCurrentIndex(3)
        assert window.task_timeline_visible_count.text() == _label(1)
        assert provider.calls == 0 and window._memory is memory and not dry.workers
    finally:
        window._set_busy(False)


def test_m153_qt_two_windows_isolated(host):
    window, _, _, _ = host
    other = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        _populate(window._task_timeline)
        window._refresh_task_timeline()
        assert window.task_timeline_visible_count.text() == _label(5)
        assert other.task_timeline_visible_count.text() == _label(0)
        other.task_timeline_interruptions_only.setChecked(True)
        assert other.task_timeline_visible_count.text() == _label(0)
    finally:
        other.close()
