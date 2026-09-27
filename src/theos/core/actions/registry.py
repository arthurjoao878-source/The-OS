from __future__ import annotations

from collections.abc import Callable

from theos.core.actions.contracts import ActionRequest, ActionResult


class ActionRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[ActionRequest], ActionResult]] = {}

    def register(self, name: str, handler: Callable[[ActionRequest], ActionResult]) -> None:
        if name in self._handlers:
            raise ValueError(f"Action already registered: {name}")
        self._handlers[name] = handler

    def execute(self, request: ActionRequest) -> ActionResult:
        handler = self._handlers.get(request.action)
        if handler is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"A ação {request.action!r} não está registrada.",
                error_code="ACTION_NOT_REGISTERED",
            )
        return handler(request)