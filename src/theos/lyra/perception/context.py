from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock

from theos.core.actions.contracts import ActionRequest, ActionResult

DEFAULT_MAX_OBSERVATIONS = 8
MAX_PERCEPTION_OBSERVATIONS = 32
MAX_PERCEPTION_ACTION_CHARS = 120
MAX_PERCEPTION_MESSAGE_CHARS = 240


@dataclass(frozen=True, slots=True)
class PerceptionObservation:
    action: str
    success: bool
    message: str
    error_code: str | None
    effect_dispatched: bool | None
    postcondition_verified: bool | None

    def __post_init__(self) -> None:
        normalized_action = self.action.strip()
        normalized_message = " ".join(self.message.split())
        if not normalized_action:
            raise ValueError("action must not be blank")
        if len(normalized_action) > MAX_PERCEPTION_ACTION_CHARS:
            raise ValueError("action is too long")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if not normalized_message:
            raise ValueError("message must not be blank")
        if len(normalized_message) > MAX_PERCEPTION_MESSAGE_CHARS:
            raise ValueError("message is too long")
        if self.error_code is not None and (
            not isinstance(self.error_code, str) or not self.error_code.strip()
        ):
            raise TypeError("error_code must be a non-blank string or None")
        if self.effect_dispatched is not None and not isinstance(
            self.effect_dispatched, bool
        ):
            raise TypeError("effect_dispatched must be bool or None")
        if self.postcondition_verified is not None and not isinstance(
            self.postcondition_verified, bool
        ):
            raise TypeError("postcondition_verified must be bool or None")
        object.__setattr__(self, "action", normalized_action)
        object.__setattr__(self, "message", normalized_message)
        if self.error_code is not None:
            object.__setattr__(self, "error_code", self.error_code.strip())


class PerceptionContext:
    """Bounded process-local summaries of The Hands action results for LYRA."""

    def __init__(self, *, max_observations: int = DEFAULT_MAX_OBSERVATIONS) -> None:
        if (
            not isinstance(max_observations, int)
            or isinstance(max_observations, bool)
            or max_observations < 1
            or max_observations > MAX_PERCEPTION_OBSERVATIONS
        ):
            raise ValueError(
                f"max_observations must be between 1 and {MAX_PERCEPTION_OBSERVATIONS}"
            )
        self._observations: deque[PerceptionObservation] = deque(
            maxlen=max_observations
        )
        self._lock = Lock()

    @property
    def max_observations(self) -> int:
        maxlen = self._observations.maxlen
        if maxlen is None:
            raise RuntimeError("perception context must be bounded")
        return maxlen

    def record(
        self,
        request: ActionRequest,
        result: ActionResult,
    ) -> PerceptionObservation:
        if request.request_id != result.request_id:
            raise ValueError("action result request_id does not match request")

        normalized_message = " ".join(result.message.split())
        if not normalized_message:
            raise ValueError("action result message must not be blank")
        if len(normalized_message) > MAX_PERCEPTION_MESSAGE_CHARS:
            normalized_message = (
                normalized_message[: MAX_PERCEPTION_MESSAGE_CHARS - 3] + "..."
            )

        observation = PerceptionObservation(
            action=request.action,
            success=result.success,
            message=normalized_message,
            error_code=result.error_code,
            effect_dispatched=result.effect_dispatched,
            postcondition_verified=result.postcondition_verified,
        )
        with self._lock:
            self._observations.append(observation)
        return observation

    def snapshot(self) -> tuple[PerceptionObservation, ...]:
        with self._lock:
            return tuple(self._observations)

    def clear(self) -> None:
        with self._lock:
            self._observations.clear()
