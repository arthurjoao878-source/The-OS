from __future__ import annotations

from enum import StrEnum
from threading import Condition


class ExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class ExecutionControl:
    """Thread-safe cooperative pause/resume/cancel control for a running LYRA task."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._status = ExecutionStatus.RUNNING

    @property
    def status(self) -> ExecutionStatus:
        with self._condition:
            return self._status

    def pause(self) -> bool:
        with self._condition:
            if self._status is not ExecutionStatus.RUNNING:
                return False
            self._status = ExecutionStatus.PAUSED
            return True

    def resume(self) -> bool:
        with self._condition:
            if self._status is not ExecutionStatus.PAUSED:
                return False
            self._status = ExecutionStatus.RUNNING
            self._condition.notify_all()
            return True

    def cancel(self) -> bool:
        with self._condition:
            if self._status is ExecutionStatus.CANCELLED:
                return False
            self._status = ExecutionStatus.CANCELLED
            self._condition.notify_all()
            return True

    def checkpoint(self) -> bool:
        """Block while paused; return False once cancellation has been requested."""
        with self._condition:
            while self._status is ExecutionStatus.PAUSED:
                self._condition.wait()
            return self._status is not ExecutionStatus.CANCELLED
