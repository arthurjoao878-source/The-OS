from __future__ import annotations

from threading import Event, Thread

from theos.lyra.execution import ExecutionControl, ExecutionStatus


def test_pause_blocks_checkpoint_until_resume() -> None:
    control = ExecutionControl()
    entered = Event()
    finished = Event()
    result: list[bool] = []

    assert control.pause() is True
    assert control.status is ExecutionStatus.PAUSED

    def worker() -> None:
        entered.set()
        result.append(control.checkpoint())
        finished.set()

    thread = Thread(target=worker)
    thread.start()

    assert entered.wait(timeout=1.0) is True
    assert finished.wait(timeout=0.05) is False

    assert control.resume() is True
    assert finished.wait(timeout=1.0) is True
    thread.join(timeout=1.0)

    assert result == [True]
    assert control.status is ExecutionStatus.RUNNING


def test_cancel_unblocks_paused_checkpoint() -> None:
    control = ExecutionControl()
    entered = Event()
    finished = Event()
    result: list[bool] = []

    control.pause()

    def worker() -> None:
        entered.set()
        result.append(control.checkpoint())
        finished.set()

    thread = Thread(target=worker)
    thread.start()

    assert entered.wait(timeout=1.0) is True
    assert control.cancel() is True
    assert finished.wait(timeout=1.0) is True
    thread.join(timeout=1.0)

    assert result == [False]
    assert control.status is ExecutionStatus.CANCELLED
