from __future__ import annotations

from uuid import uuid4

import pytest

from theos.core.actions.contracts import ActionRequest, ActionResult
from theos.lyra.perception import (
    DEFAULT_MAX_OBSERVATIONS,
    MAX_PERCEPTION_MESSAGE_CHARS,
    PerceptionContext,
)


def _result(
    request: ActionRequest,
    *,
    success: bool = True,
    message: str = "observado",
    evidence: dict[str, object] | None = None,
    error_code: str | None = None,
    effect_dispatched: bool | None = None,
    postcondition_verified: bool | None = None,
) -> ActionResult:
    return ActionResult(
        request_id=request.request_id,
        success=success,
        message=message,
        evidence={} if evidence is None else evidence,
        error_code=error_code,
        effect_dispatched=effect_dispatched,
        postcondition_verified=postcondition_verified,
    )


def test_perception_context_starts_empty_and_bounded() -> None:
    context = PerceptionContext()

    assert context.max_observations == DEFAULT_MAX_OBSERVATIONS
    assert context.snapshot() == ()


def test_perception_context_records_safe_action_summary() -> None:
    context = PerceptionContext()
    request = ActionRequest(action="window_snapshot", arguments={"secret": "do-not-copy"})
    result = _result(
        request,
        message="Janela observada.",
        evidence={"raw_hwnd": 12345, "content": "do-not-copy"},
        effect_dispatched=False,
        postcondition_verified=True,
    )

    observation = context.record(request, result)

    assert observation.action == "window_snapshot"
    assert observation.success is True
    assert observation.message == "Janela observada."
    assert observation.effect_dispatched is False
    assert observation.postcondition_verified is True


def test_perception_context_normalizes_and_truncates_message() -> None:
    context = PerceptionContext()
    request = ActionRequest(action="inspect_path")
    message = "  começo\n" + ("x" * 400) + "  "

    observation = context.record(request, _result(request, message=message))

    assert "\n" not in observation.message
    assert len(observation.message) == MAX_PERCEPTION_MESSAGE_CHARS
    assert observation.message.endswith("...")


def test_perception_context_evicts_oldest_observation() -> None:
    context = PerceptionContext(max_observations=2)
    requests = [ActionRequest(action=f"action_{index}") for index in range(3)]
    for request in requests:
        context.record(request, _result(request, message=request.action))

    assert tuple(item.action for item in context.snapshot()) == (
        "action_1",
        "action_2",
    )


def test_perception_context_rejects_mismatched_request_id() -> None:
    context = PerceptionContext()
    request = ActionRequest(action="window_snapshot")
    mismatched = ActionResult(
        request_id=uuid4(),
        success=True,
        message="resultado de outra requisição",
    )

    with pytest.raises(ValueError, match="request_id"):
        context.record(request, mismatched)


def test_perception_context_clear_removes_process_local_observations() -> None:
    context = PerceptionContext()
    request = ActionRequest(action="window_snapshot")
    context.record(request, _result(request))

    context.clear()

    assert context.snapshot() == ()


def test_perception_context_rejects_unbounded_capacity() -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        PerceptionContext(max_observations=0)
    with pytest.raises(ValueError, match="between 1 and"):
        PerceptionContext(max_observations=33)


def test_perception_observation_does_not_copy_arguments_or_raw_evidence() -> None:
    context = PerceptionContext()
    request = ActionRequest(action="read_text_file", arguments={"path": "secret.txt"})
    observation = context.record(
        request,
        _result(request, evidence={"content": "top secret", "sha256": "abc"}),
    )

    assert not hasattr(observation, "arguments")
    assert not hasattr(observation, "evidence")
    assert "secret.txt" not in repr(observation)
    assert "top secret" not in repr(observation)
