from __future__ import annotations

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import InvokeSemanticButtonAction
from theos.core.tools import (
    ToolCall,
    ToolValidationError,
    build_assistant_tool_catalog,
    build_default_tool_catalog,
)
from theos.core.window_observations import build_window_observation_handle
from theos.integrations.ai.openai_responses import _SYSTEM_INSTRUCTIONS
from theos.lyra.execution.composed_workflow import (
    WorkflowDomain,
    workflow_domain_for_action,
)


class _FakeSemanticButtonAdapter:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[
            tuple[int, str, str, str, str, int | None]
        ] = []

    def invoke_semantic_button(
        self,
        pid: int,
        title: str,
        target_token: str,
        control_token: str,
        name: str,
        control_id: int | None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                pid,
                title,
                target_token,
                control_token,
                name,
                control_id,
            )
        )
        if self.error is not None:
            raise RuntimeError(self.error)
        return {
            "pid": pid,
            "title": title,
            "target_token": target_token,
            "control_token": control_token,
            "role": "button",
            "name": name,
            "class_name": "Button",
            "control_id": control_id,
            "enabled_before": True,
            "visible_before": True,
            "semantic_invoke_dispatched": True,
            "coordinate_action_dispatched": False,
            "cursor_moved": False,
            "content_effect_verified": False,
            "raw_hwnd_exposed": False,
        }


def _request() -> ActionRequest:
    token = "a" * 64
    return ActionRequest(
        action="invoke_semantic_button",
        arguments={
            "pid": 4321,
            "title": "Janela de teste",
            "target_token": token,
            "observation_handle": build_window_observation_handle(token),
            "control_token": "b" * 64,
            "role": "button",
            "name": "Salvar",
            "class_name": "Button",
            "control_id": 100,
            "enabled": True,
        },
    )


def _approved_request(
    action: InvokeSemanticButtonAction,
) -> ActionRequest:
    request = _request()
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)
    return request


def test_semantic_button_preview_is_bound_and_adapter_free() -> None:
    adapter = _FakeSemanticButtonAdapter()
    action = InvokeSemanticButtonAction(adapter)
    request = _request()

    assert action.risk is ActionRisk.CONFIRM
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "ACIONAR BOTÃO SEMÂNTICO NATIVO" in preview.text
    assert "Salvar" in preview.text
    assert "BM_CLICK" in preview.text
    assert "não usa coordenadas" in preview.text
    assert len(preview.execution_guard) == 7
    assert adapter.calls == []


def test_semantic_button_preview_blocks_invalid_button_metadata() -> None:
    adapter = _FakeSemanticButtonAdapter()
    action = InvokeSemanticButtonAction(adapter)
    request = _request()
    request.arguments["role"] = "label"

    preview = action.confirmation_preview(request)

    assert preview.allowed is False
    assert adapter.calls == []


def test_semantic_button_execute_requires_approved_preview_guard() -> None:
    adapter = _FakeSemanticButtonAdapter()
    action = InvokeSemanticButtonAction(adapter)

    result = action.execute(_request())

    assert result.success is False
    assert result.error_code == "SEMANTIC_BUTTON_PREVIEW_REQUIRED"
    assert adapter.calls == []


def test_semantic_button_executes_exact_approved_control() -> None:
    adapter = _FakeSemanticButtonAdapter()
    action = InvokeSemanticButtonAction(adapter)
    request = _approved_request(action)

    result = action.execute(request)

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is None
    assert result.evidence["semantic_invoke_dispatched"] is True
    assert result.evidence["coordinate_action_dispatched"] is False
    assert result.evidence["content_effect_verified"] is False
    assert adapter.calls == [
        (
            4321,
            "Janela de teste",
            "a" * 64,
            "b" * 64,
            "Salvar",
            100,
        )
    ]


def test_semantic_button_rejects_expired_window_observation() -> None:
    adapter = _FakeSemanticButtonAdapter()
    action = InvokeSemanticButtonAction(adapter)
    request = _request()
    request.arguments["observation_handle"] = build_window_observation_handle(
        "a" * 64,
        now=1,
    )

    preview = action.confirmation_preview(request)

    assert preview.allowed is False
    assert adapter.calls == []


def test_semantic_button_maps_stale_control_without_dispatch_claim() -> None:
    adapter = _FakeSemanticButtonAdapter(
        error="SEMANTIC_CONTROL_NOT_FOUND_OR_STALE"
    )
    action = InvokeSemanticButtonAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_CONTROL_NOT_FOUND_OR_STALE"
    assert result.effect_dispatched is None


def test_semantic_button_maps_disabled_control_without_dispatch_claim() -> None:
    adapter = _FakeSemanticButtonAdapter(
        error="SEMANTIC_CONTROL_DISABLED"
    )
    action = InvokeSemanticButtonAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_CONTROL_DISABLED"
    assert result.effect_dispatched is None


def test_catalog_builds_strict_semantic_button_request() -> None:
    catalog = build_default_tool_catalog()
    token = "c" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="invoke_semantic_button",
            arguments={
                "pid": 987,
                "title": " Janela ",
                "target_token": token,
                "observation_handle": handle,
                "control_token": "d" * 64,
                "role": "button",
                "name": " OK ",
                "class_name": "Button",
                "control_id": None,
                "enabled": True,
            },
        )
    )

    assert request.action == "invoke_semantic_button"
    assert request.arguments["title"] == "Janela"
    assert request.arguments["name"] == "OK"
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item
        for item in catalog.definitions()
        if item.name == "invoke_semantic_button"
    )
    assert set(definition.parameters["required"]) == set(
        definition.parameters["properties"]
    )
    assert definition.parameters["additionalProperties"] is False


def test_catalog_rejects_fabricated_semantic_button_rows() -> None:
    catalog = build_default_tool_catalog()
    token = "e" * 64
    base = {
        "pid": 987,
        "title": "Janela",
        "target_token": token,
        "observation_handle": build_window_observation_handle(token),
        "control_token": "f" * 64,
        "role": "button",
        "name": "OK",
        "class_name": "Button",
        "control_id": 1,
        "enabled": True,
    }

    for changed in (
        {"control_token": "INVALID"},
        {"role": "label"},
        {"class_name": "Static"},
        {"enabled": False},
        {"control_id": -1},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="invoke_semantic_button",
                    arguments={**base, **changed},
                )
            )


def test_semantic_button_is_normal_window_capability_with_guidance() -> None:
    full = {item.name for item in build_default_tool_catalog().definitions()}
    assistant = {
        item.name for item in build_assistant_tool_catalog().definitions()
    }
    registry = set(build_action_registry().names())

    assert len(full) == 62
    assert len(assistant) == 46
    assert "invoke_semantic_button" in full
    assert "invoke_semantic_button" in assistant
    assert "invoke_semantic_button" in registry
    assert (
        workflow_domain_for_action("invoke_semantic_button")
        is WorkflowDomain.WINDOW
    )
    assert "semantic_window_snapshot" in _SYSTEM_INSTRUCTIONS
    assert "invoke_semantic_button" in _SYSTEM_INSTRUCTIONS
    assert "control_token" in _SYSTEM_INSTRUCTIONS
