from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk

ActionHandler = Callable[[ActionRequest], ActionResult]
RiskResolver = Callable[[ActionRequest], ActionRisk]


@dataclass(frozen=True, slots=True)
class _ActionRegistration:
    handler: ActionHandler
    risk_resolver: RiskResolver


class ActionRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, _ActionRegistration] = {}

    def register(
        self,
        name: str,
        handler: ActionHandler,
        *,
        risk: ActionRisk | RiskResolver = ActionRisk.NORMAL,
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
