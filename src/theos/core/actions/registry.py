from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)

ActionHandler = Callable[[ActionRequest], ActionResult]
RiskResolver = Callable[[ActionRequest], ActionRisk]
PreviewResolver = Callable[[ActionRequest], ConfirmationPreview]


@dataclass(frozen=True, slots=True)
class _ActionRegistration:
    handler: ActionHandler
    risk_resolver: RiskResolver
    preview_resolver: PreviewResolver | None


class ActionRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, _ActionRegistration] = {}

    def register(
        self,
        name: str,
        handler: ActionHandler,
        *,
        risk: ActionRisk | RiskResolver = ActionRisk.NORMAL,
        confirmation_preview: PreviewResolver | None = None,
    ) -> None:
        if name in self._registrations:
            raise ValueError(f"Action already registered: {name}")

        risk_resolver: RiskResolver
        if isinstance(risk, ActionRisk):
            risk_resolver = lambda _request, value=risk: value
        else:
            risk_resolver = risk

        self._registrations[name] = _ActionRegistration(
            handler=handler,
            risk_resolver=risk_resolver,
            preview_resolver=confirmation_preview,
        )

    def contains(self, name: str) -> bool:
        return name in self._registrations

    def names(self) -> tuple[str, ...]:
        return tuple(self._registrations)

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        registration = self._registrations.get(request.action)
        if registration is None:
            raise KeyError(f"Action not registered: {request.action}")
        risk = registration.risk_resolver(request)
        if not isinstance(risk, ActionRisk):
            raise TypeError("risk resolver must return ActionRisk")
        return risk

    def confirmation_preview_for(
        self,
        request: ActionRequest,
    ) -> ConfirmationPreview | None:
        registration = self._registrations.get(request.action)
        if registration is None:
            raise KeyError(f"Action not registered: {request.action}")
        if registration.preview_resolver is None:
            return None
        preview = registration.preview_resolver(request)
        if not isinstance(preview, ConfirmationPreview):
            raise TypeError("preview resolver must return ConfirmationPreview")
        return preview

    def execute(self, request: ActionRequest) -> ActionResult:
        registration = self._registrations.get(request.action)
        if registration is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"A ação {request.action!r} não está registrada.",
                error_code="ACTION_NOT_REGISTERED",
            )
        return registration.handler(request)
