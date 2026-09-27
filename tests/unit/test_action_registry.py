from theos.core.actions.contracts import ActionRequest
from theos.core.actions.registry import ActionRegistry


def test_unknown_action_is_rejected() -> None:
    registry = ActionRegistry()
    result = registry.execute(ActionRequest(action="does_not_exist"))
    assert result.success is False
    assert result.error_code == "ACTION_NOT_REGISTERED"