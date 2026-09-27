from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.core.actions.registry import ActionRegistry
from theos.lyra.execution import SequentialActionExecutor


def test_sequence_executes_in_order_and_completes() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        name = str(request.arguments["application"])
        executed.append(name)
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"{name} aberto.",
        )

    registry.register("open_application", handler)
    executor = SequentialActionExecutor(registry)
    requests = (
        ActionRequest(action="open_application", arguments={"application": "Notepad"}),
        ActionRequest(action="open_application", arguments={"application": "Chrome"}),
    )

    result = executor.execute(requests)

    assert executed == ["Notepad", "Chrome"]
    assert result.success is True
    assert result.completed_steps == 2
    assert result.planned_steps == 2


def test_sequence_stops_after_first_failed_verification() -> None:
    executed: list[str] = []
    registry = ActionRegistry()

    def handler(request: ActionRequest) -> ActionResult:
        name = str(request.arguments["application"])
        executed.append(name)
        success = name != "Fail"
        return ActionResult(
            request_id=request.request_id,
            success=success,
            message="ok" if success else "falhou",
            error_code=None if success else "ACTION_VERIFICATION_FAILED",
        )

    registry.register("open_application", handler)
    executor = SequentialActionExecutor(registry)
    requests = (
        ActionRequest(action="open_application", arguments={"application": "First"}),
        ActionRequest(action="open_application", arguments={"application": "Fail"}),
        ActionRequest(action="open_application", arguments={"application": "Never"}),
    )

    result = executor.execute(requests)

    assert executed == ["First", "Fail"]
    assert result.success is False
    assert result.completed_steps == 2
    assert result.planned_steps == 3
