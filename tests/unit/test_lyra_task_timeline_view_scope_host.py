from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow
from theos.shell.assistant.task_timeline import TaskTimeline
from theos.shell.assistant.workflow_progress import HostWorkflowProgressView

START = "Tarefa: iniciada · 0/4 etapas"
PENDING = "Tarefa: cancelamento solicitado · aguardando confirmação"
CANCELLED = "Tarefa: cancelada · 0/4 etapas"
FAILED = "Tarefa: falhou · 1/4 etapas · sistema"
SUCCESS = "Ação direta: pós-condição verificada · open_application"


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


def _populate(timeline):
    for text, terminal in (
        (START, False), (PENDING, False), (CANCELLED, True),
        (FAILED, True), (SUCCESS, True),
    ):
        assert timeline.record(HostWorkflowProgressView(text=text, terminal=terminal))


@pytest.mark.parametrize("category", ["all", "pending", "cancelled", "failed", "invalid", None, True])
def test_m154_full_view_inert_category(category):
    model = TaskTimeline()
    _populate(model)
    assert model.visible_view_scope_label(
        interruptions_only=False, category=category  # type: ignore[arg-type]
    ) == "Visão: histórico completo"


@pytest.mark.parametrize("category,expected", [
    ("all", "Visão: interrupções · todas"),
    ("pending", "Visão: interrupções · pendentes"),
    ("cancelled", "Visão: interrupções · canceladas"),
    ("failed", "Visão: interrupções · falhas"),
])
def test_m154_category_fixed_labels(category, expected):
    assert TaskTimeline().visible_view_scope_label(
        interruptions_only=True, category=category
    ) == expected


@pytest.mark.parametrize("category", ["", "INVALID", "PENDING", 0, None, True, [], {}])
def test_m154_invalid_active_category_fails_closed(category):
    model = TaskTimeline()
    _populate(model)
    assert model.visible_view_scope_label(
        interruptions_only=True, category=category  # type: ignore[arg-type]
    ) == "Visão: indisponível"


@pytest.mark.parametrize("enabled", [None, 0, 1, "yes", [], {}])
def test_m154_invalid_filter_boolean_fails_closed(enabled):
    assert TaskTimeline().visible_view_scope_label(
        interruptions_only=enabled, category="all"  # type: ignore[arg-type]
    ) == "Visão: indisponível"


def test_m154_fixed_label_does_not_mutate_events_or_counts():
    model = TaskTimeline()
    _populate(model)
    before = (model.snapshot(), model.interruption_count_label(),
              model.interruption_breakdown_label(), model.summary())
    for category in ("all", "pending", "cancelled", "failed", None, "SECRET_PATH"):
        for enabled in (True, False):
            assert model.visible_view_scope_label(
                interruptions_only=enabled, category=category  # type: ignore[arg-type]
            ).startswith("Visão: ")
    assert before == (model.snapshot(), model.interruption_count_label(),
                      model.interruption_breakdown_label(), model.summary())


def test_m154_default_label_identity_and_panel_hidden(host):
    window, provider, _, pool = host
    label = window.task_timeline_view_scope
    assert label.objectName() == "lyra_task_timeline_view_scope"
    assert label.text() == "Visão: histórico completo"
    assert not label.isHidden()
    assert window.task_timeline_view.isHidden()
    assert provider.calls == 0 and not pool.workers


def test_m154_qt_category_inert_until_filter(host):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruption_category.setCurrentIndex(3)
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"
    assert window.task_timeline_visible_count.text() == "Na lista: 5/12 eventos recentes"
    window.task_timeline_interruptions_only.setChecked(True)
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · falhas"
    assert window.task_timeline_visible_count.text() == "Na lista: 1/12 eventos recentes"


def test_m154_qt_category_cycle_shares_view_refresh(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · todas"
    for expected in ("pendentes", "canceladas", "falhas", "todas"):
        window.task_timeline_interruption_category_cycle_shortcut.activated.emit()
        assert window.task_timeline_view_scope.text() == "Visão: interrupções · " + expected
    window.task_timeline_interruptions_shortcut.activated.emit()
    assert window.task_timeline_view_scope.text() == "Visão: histórico completo"


def test_m154_qt_panel_toggle_does_not_change_view_scope(host):
    window, _, _, _ = host
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    for _ in range(2):
        window.task_timeline_toggle_shortcut.activated.emit()
        assert window.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"


def test_m154_qt_corrupted_category_fail_closed(host):
    window, _, _, _ = host
    combo = window.task_timeline_interruption_category
    window.task_timeline_interruptions_only.setChecked(True)
    combo.setItemData(0, "PRIVATE_BAD_INPUT")
    window._refresh_task_timeline()
    assert window.task_timeline_view_scope.text() == "Visão: indisponível"
    assert "PRIVATE_BAD_INPUT" not in window.task_timeline_view_scope.text()
    assert window.task_timeline_visible_count.text() == "Na lista: 0/12 eventos recentes"
    combo.setItemData(0, "all")
    window._refresh_task_timeline()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · todas"


def test_m154_qt_denied_reset_preserves_scope(host, monkeypatch):
    window, _, _, _ = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(2)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    window.session_reset.click()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · canceladas"
    assert len(window._task_timeline.snapshot()) == 5


def test_m154_qt_accepted_reset_retains_scope(host, monkeypatch):
    window, provider, memory, pool = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    window.session_reset.click()
    assert window.task_timeline_view_scope.text() == "Visão: interrupções · falhas"
    assert window.task_timeline_visible_count.text() == "Na lista: 0/12 eventos recentes"
    assert not window._task_timeline.snapshot()
    assert window._memory is memory and provider.calls == 0 and not pool.workers


def test_m154_qt_busy_presentation_remains_passive(host):
    window, provider, memory, pool = host
    _populate(window._task_timeline)
    window._refresh_task_timeline()
    window._set_busy(True)
    try:
        window.task_timeline_interruptions_only.setChecked(True)
        window.task_timeline_interruption_category.setCurrentIndex(1)
        assert window.task_timeline_view_scope.text() == "Visão: interrupções · pendentes"
        assert window._memory is memory and provider.calls == 0 and not pool.workers
    finally:
        window._set_busy(False)


def test_m154_qt_two_windows_isolated(host):
    window, _, _, _ = host
    second = MainWindow(
        ActionRegistry(), object(), ControlledProvider(), build_default_tool_catalog()
    )
    try:
        window.task_timeline_interruptions_only.setChecked(True)
        window.task_timeline_interruption_category.setCurrentIndex(3)
        assert window.task_timeline_view_scope.text() == "Visão: interrupções · falhas"
        assert second.task_timeline_view_scope.text() == "Visão: histórico completo"
        second.task_timeline_interruption_category_cycle_shortcut.activated.emit()
        assert second.task_timeline_view_scope.text() == "Visão: histórico completo"
        assert window.task_timeline_view_scope.text() == "Visão: interrupções · falhas"
    finally:
        second.close()
