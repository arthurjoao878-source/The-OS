from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.actions.registry import ActionRegistry


def test_unknown_action_is_rejected() -> None:
    registry = ActionRegistry()
    result = registry.execute(ActionRequest(action="does_not_exist"))
    assert result.success is False
    assert result.error_code == "ACTION_NOT_REGISTERED"


def test_registry_exposes_only_registered_action_names() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="ok",
        )

    registry.register("known_action", handler)

    assert registry.contains("known_action") is True
    assert registry.contains("unknown_action") is False
    assert registry.names() == ("known_action",)


def test_registry_defaults_to_normal_risk() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="ok",
        )

    registry.register("known_action", handler)
    request = ActionRequest(action="known_action")

    assert registry.risk_for(request) is ActionRisk.NORMAL


def test_registry_uses_local_request_risk_resolver() -> None:
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message="ok",
        )

    def risk_for(request: ActionRequest) -> ActionRisk:
        if request.arguments.get("sensitive") is True:
            return ActionRisk.CONFIRM
        return ActionRisk.NORMAL

    registry.register("known_action", handler, risk=risk_for)

    assert registry.risk_for(
        ActionRequest(
            action="known_action",
            arguments={"sensitive": True},
        )
    ) is ActionRisk.CONFIRM
