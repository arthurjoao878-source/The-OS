from theos.core.actions.contracts import ActionRequest, ActionResult
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
