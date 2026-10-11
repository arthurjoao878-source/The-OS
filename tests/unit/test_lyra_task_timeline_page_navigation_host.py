from __future__ import annotations

import pytest
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


def test_m160_button_identity_and_default(host):
    window,provider,memory,dry=host
    previous=window.task_timeline_page_previous
    following=window.task_timeline_page_next
    assert previous.objectName()=="lyra_task_timeline_page_previous"
    assert following.objectName()=="lyra_task_timeline_page_next"
    assert previous.text()=="Página anterior"
    assert following.text()=="Próxima página"
    assert previous.isEnabled() and following.isEnabled()
    assert "histórico" in previous.toolTip() and "histórico" in following.toolTip()
    assert window.task_timeline_view.isHidden()
    check_safe(window,provider,memory,dry,snapshot(window))


@pytest.mark.parametrize('direction',[-1,1])
def test_m160_hidden_panel_revealed_without_model_change(host,direction):
    window,provider,memory,dry=host
    populate_twelve(window)
    window.show()
    QApplication.processEvents()
    before=snapshot(window)
    assert window.task_timeline_view.isHidden()
    page(window,direction)
    assert not window.task_timeline_view.isHidden()
    check_safe(window,provider,memory,dry,before)


@pytest.mark.parametrize('direction',[-1,1])
def test_m160_page_step_exact_and_clamped(host,direction):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    before=snapshot(window)
    initial=(bar.maximum() if direction<0 else bar.minimum())
    bar.setValue(initial)
    old=bar.value()
    expected=max(bar.minimum(),min(bar.maximum(),old+direction*max(1,bar.pageStep())))
    page(window,direction)
    assert bar.value()==expected
    check_safe(window,provider,memory,dry,before)


@pytest.mark.parametrize('direction',[-1,1])
def test_m160_boundary_idempotence(host,direction):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    before=snapshot(window)
    bound=bar.minimum() if direction<0 else bar.maximum()
    bar.setValue(bound)
    for _ in range(4):
        page(window,direction)
    assert bar.value()==bound
    check_safe(window,provider,memory,dry,before)


def test_m160_first_last_and_paging_compatible(host):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    before=snapshot(window)
    window.task_timeline_jump_first.click()
    assert bar.value()==bar.minimum()
    page(window,1)
    assert bar.value()>bar.minimum()
    window.task_timeline_jump_latest.click()
    assert bar.value()==bar.maximum()
    page(window,-1)
    assert bar.value()<bar.maximum()
    window.task_timeline_jump_first_shortcut.activated.emit()
    assert bar.value()==bar.minimum()
    window.task_timeline_jump_latest_shortcut.activated.emit()
    assert bar.value()==bar.maximum()
    check_safe(window,provider,memory,dry,before)


@pytest.mark.parametrize('direction',[-1,1])
def test_m160_disabled_button_blocks_click_and_direct_handler(host,direction):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    bar.setValue(bar.maximum() if direction<0 else bar.minimum())
    before=snapshot(window)
    old=bar.value()
    button=window.task_timeline_page_previous if direction<0 else window.task_timeline_page_next
    button.setEnabled(False)
    try:
        page(window,direction)
        window._page_task_timeline(direction)
        assert bar.value()==old
        check_safe(window,provider,memory,dry,before)
    finally:
        button.setEnabled(True)


@pytest.mark.parametrize('direction',[-1,1])
def test_m160_disabled_timeline_refuses_navigation(host,direction):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    bar.setValue(bar.maximum() if direction<0 else bar.minimum())
    old=bar.value()
    before=snapshot(window)
    window.task_timeline_view.setEnabled(False)
    try:
        page(window,direction)
        window._page_task_timeline(direction)
        assert bar.value()==old
        check_safe(window,provider,memory,dry,before)
    finally:
        window.task_timeline_view.setEnabled(True)


@pytest.mark.parametrize('invalid',[0,2,-2,True,False,None,'1'])
def test_m160_invalid_direct_direction_fails_closed(host,invalid):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    bar.setValue(bar.maximum()//2)
    old=bar.value()
    before=snapshot(window)
    window._page_task_timeline(invalid)
    assert bar.value()==old
    check_safe(window,provider,memory,dry,before)


@pytest.mark.parametrize('index',[0,1,2,3])
def test_m160_filtered_categories_unchanged(host,index):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(index)
    QApplication.processEvents()
    before=snapshot(window)
    old=(window.task_timeline_visible_count.text(),window.task_timeline_view_scope.text(),
         window.task_timeline_view.toPlainText())
    bar.setValue(bar.maximum())
    page(window,-1)
    page(window,1)
    assert window.task_timeline_interruptions_only.isChecked()
    assert window.task_timeline_interruption_category.currentIndex()==index
    assert (window.task_timeline_visible_count.text(),window.task_timeline_view_scope.text(),
            window.task_timeline_view.toPlainText())==old
    check_safe(window,provider,memory,dry,before)


def test_m160_inert_category_full_history(host):
    window,provider,memory,dry=host
    _,bar=create_view(window)
    window.task_timeline_interruption_category.setCurrentIndex(3)
    assert not window.task_timeline_interruptions_only.isChecked()
    before=snapshot(window)
    old=window.task_timeline_view.toPlainText()
    bar.setValue(bar.maximum())
    page(window,-1)
    assert window.task_timeline_view.toPlainText()==old
    check_safe(window,provider,memory,dry,before)


def test_m160_malformed_category_keeps_fixed_safe_text(host):
    window,provider,memory,dry=host
    create_view(window)
    window.task_timeline_interruptions_only.setChecked(True)
    window.task_timeline_interruption_category.setCurrentIndex(1)
    window.task_timeline_interruption_category.setItemData(1,'RAW_DANGEROUS_DATA')
    window._refresh_task_timeline()
    old=window.task_timeline_view.toPlainText()
    before=snapshot(window)
    page(window,1)
    page(window,-1)
    assert window.task_timeline_view.toPlainText()==old
    assert 'RAW_DANGEROUS_DATA' not in old
    check_safe(window,provider,memory,dry,before)


def test_m160_no_deletion_or_reset_after_page(host):
    window,provider,memory,dry=host
    create_view(window)
    before=snapshot(window)
    window.task_timeline_view.setPlainText(window.task_timeline_view.toPlainText())
    page(window,1)
    page(window,-1)
    check_safe(window,provider,memory,dry,before)


def test_m160_two_window_isolation(host):
    window,provider,memory,dry=host
    other=MainWindow(ActionRegistry(),object(),ControlledProvider(),build_default_tool_catalog())
    try:
        _,left=create_view(window)
        _,right=create_view(other)
        left.setValue(left.maximum())
        right.setValue(right.minimum())
        other_before=right.value()
        page(window,-1)
        assert left.value()<left.maximum()
        assert right.value()==other_before
        assert other.task_timeline_page_previous.parent() is not window
        check_safe(window,provider,memory,dry,snapshot(window))
    finally:
        other.close()


def test_m160_busy_dry_task_presentation_only(host):
    window,provider,memory,dry=host
    create_view(window)
    window._start_tool_task('simulação',())
    assert len(dry.workers)==1 and provider.calls==0
    populate_twelve(window)
    QApplication.processEvents()
    bar=window.task_timeline_view.verticalScrollBar()
    bar.setValue(bar.maximum())
    prev=bar.value()
    page(window,-1)
    assert bar.value()<=prev
    page(window,1)
    assert len(dry.workers)==1 and provider.calls==0
    assert window._memory is memory
    assert window.task_timeline_view.isReadOnly()


@pytest.mark.parametrize('accepted',[True,False])
def test_m160_reset_preserves_controls_and_semantics(host,monkeypatch,accepted):
    window,provider,memory,dry=host
    create_view(window)
    before=snapshot(window)
    monkeypatch.setattr(QMessageBox,'question',lambda *_a,**_k: (
        QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No))
    window.session_reset.click()
    if accepted:
        assert window._task_timeline.snapshot()==()
    else:
        assert snapshot(window)==before
    page(window,1)
    page(window,-1)
    assert window.task_timeline_page_previous.isEnabled()
    assert window.task_timeline_page_next.isEnabled()
    assert window._memory is memory
    assert provider.calls==0 and not dry.workers


def test_m160_short_history_no_scroll_works(host):
    window,provider,memory,dry=host
    window.show()
    QApplication.processEvents()
    before=snapshot(window)
    page(window,-1)
    page(window,1)
    assert not window.task_timeline_view.isHidden()
    check_safe(window,provider,memory,dry,before)
