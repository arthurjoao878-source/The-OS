from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

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


def view(window):
    populate(window)
    window.show()
    QApplication.processEvents()
    window.task_timeline_view.show()
    QApplication.processEvents()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()
    return bar


def midpoint(bar):
    return bar.minimum() + (bar.maximum() - bar.minimum()) // 2


def state(window):
    t = window._task_timeline
    return (t.snapshot(), t.summary(), t.interruption_count_label(),
            t.interruption_breakdown_label(),
            window.task_timeline_interruptions_only.isChecked(),
            window.task_timeline_interruption_category.currentIndex(),
            window.task_timeline_interruption_category.currentData())


def passive(window, provider, memory, dry, old_state):
    assert state(window) == old_state
    assert window._memory is memory
    assert provider.calls == 0
    assert not dry.workers
    assert window.task_timeline_view.isReadOnly()


def click(window):
    window.task_timeline_jump_middle.click()
    QApplication.processEvents()


def label(window):
    return window.task_timeline_scroll_position.text()


def assert_position(window):
    bar = window.task_timeline_view.verticalScrollBar()
    assert label(window) == window._task_timeline_scroll_position_text(
        bar.value(), bar.minimum(), bar.maximum()
    )


def test_m163_button_identity_default_and_no_permissions(host):
    window, provider, memory, dry = host
    button = window.task_timeline_jump_middle
    assert isinstance(button, QPushButton)
    assert button.objectName() == "lyra_task_timeline_jump_middle"
    assert button.text() == "Meio da lista"
    assert button.toolTip()
    assert button.isEnabled()
    assert window.task_timeline_view.isReadOnly()
    assert window.task_timeline_view.isHidden()
    assert label(window) == "Posição: sem rolagem"
    passive(window, provider, memory, dry, state(window))


def test_m163_click_on_empty_panel_safe_and_reveals(host):
    window, provider, memory, dry = host
    before = state(window)
    window.show()
    QApplication.processEvents()
    click(window)
    assert not window.task_timeline_view.isHidden()
    bar = window.task_timeline_view.verticalScrollBar()
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("origin", ("start", "end", "internal"))
def test_m163_button_uses_real_scrollbar_midpoint(host, origin):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    if origin == "start":
        bar.setValue(bar.minimum())
    elif origin == "end":
        bar.setValue(bar.maximum())
    else:
        bar.setValue(bar.minimum() + 1)
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("count", (1, 2, 8, 32))
def test_m163_repeat_clicks_are_idempotent(host, count):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    for _ in range(count):
        click(window)
        assert bar.value() == midpoint(bar)
        assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("direction", ("first", "latest"))
def test_m163_prior_jump_buttons_remain_compatible(host, direction):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    click(window)
    if direction == "first":
        window.task_timeline_jump_first.click()
        assert bar.value() == bar.minimum()
    else:
        window.task_timeline_jump_latest.click()
        assert bar.value() == bar.maximum()
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("direction", (-1, 1))
def test_m163_previous_next_page_buttons_compatible(host, direction):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    bar.setValue(bar.minimum() if direction == 1 else bar.maximum())
    target = max(bar.minimum(), min(bar.maximum(), bar.value() + direction * max(1, bar.pageStep())))
    if direction == 1:
        window.task_timeline_page_next.click()
    else:
        window.task_timeline_page_previous.click()
    assert bar.value() == target
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("key,expected", (
    (Qt.Key.Key_Home, "start"),
    (Qt.Key.Key_End, "end"),
    (Qt.Key.Key_PageUp, "page"),
    (Qt.Key.Key_PageDown, "page"),
))
def test_m163_previous_timeline_keyboard_routes_compatible(host, key, expected):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    click(window)
    window.activateWindow()
    window.transcript_find.setFocus()
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    QTest.keyClick(
        window.transcript_find, key,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert bar.minimum() <= bar.value() <= bar.maximum()
    if expected == "start":
        assert bar.value() == bar.minimum()
    elif expected == "end":
        assert bar.value() == bar.maximum()
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("category", (0, 1, 2, 3))
def test_m163_midpoint_tracks_current_filtered_view(host, category):
    window, provider, memory, dry = host
    bar = view(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    window.task_timeline_interruptions_only.setChecked(True)
    QApplication.processEvents()
    before = state(window)
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("category", (0, 1, 2, 3))
def test_m163_midpoint_inert_categories_without_active_filter(host, category):
    window, provider, memory, dry = host
    bar = view(window)
    window.task_timeline_interruption_category.setCurrentIndex(category)
    QApplication.processEvents()
    before = state(window)
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


@pytest.mark.parametrize("disabled", ("button", "view"))
def test_m163_disabled_controls_and_direct_guard_fail_closed(host, disabled):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    bar.setValue(bar.maximum())
    control = (window.task_timeline_jump_middle if disabled == "button"
               else window.task_timeline_view)
    control.setEnabled(False)
    window._jump_to_middle_task_timeline_event()
    click(window)
    QApplication.processEvents()
    assert bar.value() == bar.maximum()
    assert window.task_timeline_view.isReadOnly()
    control.setEnabled(True)
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


def test_m163_existing_hidden_view_reveals_and_updates_label(host):
    window, provider, memory, dry = host
    bar = view(window)
    before = state(window)
    window.task_timeline_view.hide()
    assert window.task_timeline_view.isHidden()
    click(window)
    assert not window.task_timeline_view.isHidden()
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)


def test_m163_malformed_category_safe_no_private_data(host):
    window, provider, memory, dry = host
    bar = view(window)
    window.task_timeline_interruption_category.setItemData(0, "RAW_SECRET")
    window.task_timeline_interruptions_only.setChecked(True)
    window._refresh_task_timeline()
    QApplication.processEvents()
    before = state(window)
    click(window)
    assert bar.value() == midpoint(bar)
    assert "RAW_SECRET" not in window.task_timeline_view.toPlainText()
    assert "RAW_SECRET" not in label(window)
    assert_position(window)
    passive(window, provider, memory, dry, before)


def test_m163_two_windows_have_independent_midpoints(host):
    window, provider, memory, dry = host
    other_provider = ControlledProvider()
    other = MainWindow(
        ActionRegistry(), object(), other_provider, build_default_tool_catalog()
    )
    try:
        left = view(window)
        right = view(other)
        before = state(window)
        right.setValue(right.maximum())
        left.setValue(left.minimum())
        click(window)
        assert left.value() == midpoint(left)
        assert right.value() == right.maximum()
        click(other)
        assert right.value() == midpoint(right)
        assert left.value() == midpoint(left)
        assert_position(window)
        assert_position(other)
        assert other_provider.calls == 0
        passive(window, provider, memory, dry, before)
    finally:
        other.close()


def test_m163_dry_busy_task_allows_passive_midpoint(host):
    window, provider, memory, dry = host
    view(window)
    window._start_tool_task("simulação", ())
    assert len(dry.workers) == 1
    assert not window.input.isEnabled()
    bar = window.task_timeline_view.verticalScrollBar()
    bar.setValue(bar.maximum())
    before = state(window)
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    assert state(window) == before
    assert provider.calls == 0 and len(dry.workers) == 1
    assert window._memory is memory


@pytest.mark.parametrize("accepted", (False, True))
def test_m163_reset_preserves_functional_button(host, monkeypatch, accepted):
    window, provider, memory, dry = host
    bar = view(window)
    click(window)
    before = state(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: (
        QMessageBox.StandardButton.Yes
        if accepted else QMessageBox.StandardButton.No
    ))
    window.session_reset.click()
    QApplication.processEvents()
    if accepted:
        assert window._task_timeline.snapshot() == ()
    else:
        assert state(window) == before
    assert window.task_timeline_jump_middle.isEnabled()
    click(window)
    assert bar.value() == midpoint(bar)
    assert_position(window)
    assert window._memory is memory
    assert provider.calls == 0 and not dry.workers


def test_m163_preserves_draft_search_and_indicator(host):
    window, provider, memory, dry = host
    bar = view(window)
    window.input.setText("RASCUNHO PRIVADO")
    window.transcript_find.setText("busca")
    before = state(window)
    click(window)
    assert window.input.text() == "RASCUNHO PRIVADO"
    assert window.transcript_find.text() == "busca"
    assert bar.value() == midpoint(bar)
    assert_position(window)
    passive(window, provider, memory, dry, before)
