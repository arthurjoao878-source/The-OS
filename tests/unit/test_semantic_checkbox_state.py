from __future__ import annotations

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import SetSemanticCheckboxStateAction
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


class _FakeSemanticCheckboxAdapter:
    def __init__(
        self,
        *,
        error: str | None = None,
        dispatched: bool = True,
    ) -> None:
        self.error = error
        self.dispatched = dispatched
        self.calls: list[
            tuple[int, str, str, str, str, int | None, bool]
        ] = []

    def set_semantic_checkbox_state(
        self,
        pid: int,
        title: str,
        target_token: str,
        control_token: str,
        name: str,
        control_id: int | None,
        checked: bool,
    ) -> dict[str, object]:
        self.calls.append(
            (
                pid,
                title,
                target_token,
                control_token,
                name,
                control_id,
                checked,
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
            "checkbox_style": "BS_AUTOCHECKBOX",
            "checked_before": False if self.dispatched else checked,
            "checked_after": checked,
            "desired_checked": checked,
            "semantic_checkbox_click_dispatched": self.dispatched,
            "coordinate_action_dispatched": False,
            "cursor_moved": False,
            "keyboard_input_dispatched": False,
            "clipboard_used": False,
            "content_effect_verified": True,
            "checkbox_postcondition_verified": True,
            "raw_hwnd_exposed": False,
        }


def _request(*, checked: bool = True) -> ActionRequest:
    token = "a" * 64
    return ActionRequest(
        action="set_semantic_checkbox_state",
        arguments={
            "pid": 4321,
            "title": "Janela de teste",
            "target_token": token,
            "observation_handle": build_window_observation_handle(token),
            "control_token": "b" * 64,
            "role": "button",
            "name": "Ativar recurso",
            "class_name": "Button",
            "control_id": 100,
            "enabled": True,
            "checked": checked,
        },
    )


def _approved_request(
    action: SetSemanticCheckboxStateAction,
    *,
    checked: bool = True,
) -> ActionRequest:
    request = _request(checked=checked)
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)
    return request


def test_semantic_checkbox_preview_binds_exact_control_and_state() -> None:
    adapter = _FakeSemanticCheckboxAdapter()
    action = SetSemanticCheckboxStateAction(adapter)
    preview = action.confirmation_preview(_request())

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "DEFINIR ESTADO DE CHECKBOX SEMÂNTICO NATIVO" in preview.text
    assert "Ativar recurso" in preview.text
    assert "marcado" in preview.text
    assert "BS_AUTOCHECKBOX" in preview.text
    assert "BM_GETCHECK" in preview.text
    assert "BM_CLICK" in preview.text
    assert len(preview.execution_guard) == 8
    assert adapter.calls == []


def test_semantic_checkbox_preview_blocks_non_button_row() -> None:
    adapter = _FakeSemanticCheckboxAdapter()
    action = SetSemanticCheckboxStateAction(adapter)
    request = _request()
    request.arguments["class_name"] = "Static"

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_checkbox_execute_requires_approved_preview_guard() -> None:
    adapter = _FakeSemanticCheckboxAdapter()
    action = SetSemanticCheckboxStateAction(adapter)

    result = action.execute(_request())

    assert result.success is False
    assert result.error_code == "SEMANTIC_CHECKBOX_PREVIEW_REQUIRED"
    assert adapter.calls == []


def test_semantic_checkbox_executes_exact_approved_state_and_verifies() -> None:
    adapter = _FakeSemanticCheckboxAdapter()
    action = SetSemanticCheckboxStateAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["semantic_checkbox_click_dispatched"] is True
    assert result.evidence["content_effect_verified"] is True
    assert result.evidence["checkbox_postcondition_verified"] is True
    assert result.evidence["desired_checked"] is True
    assert result.evidence["coordinate_action_dispatched"] is False
    assert result.evidence["keyboard_input_dispatched"] is False
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["raw_hwnd_exposed"] is False


def test_semantic_checkbox_successful_noop_is_verified_without_dispatch() -> None:
    adapter = _FakeSemanticCheckboxAdapter(dispatched=False)
    action = SetSemanticCheckboxStateAction(adapter)

    result = action.execute(_approved_request(action, checked=False))

    assert result.success is True
    assert result.effect_dispatched is False
    assert result.postcondition_verified is True
    assert result.evidence["semantic_checkbox_click_dispatched"] is False
    assert result.evidence["desired_checked"] is False
    assert result.evidence["checked_after"] is False


def test_semantic_checkbox_rejects_expired_window_observation() -> None:
    adapter = _FakeSemanticCheckboxAdapter()
    action = SetSemanticCheckboxStateAction(adapter)
    request = _request()
    request.arguments["observation_handle"] = build_window_observation_handle(
        "a" * 64,
        now=1,
    )

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_checkbox_maps_unsupported_style_without_dispatch_claim() -> None:
    adapter = _FakeSemanticCheckboxAdapter(
        error="SEMANTIC_CHECKBOX_UNSUPPORTED_STYLE"
    )
    action = SetSemanticCheckboxStateAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_CHECKBOX_UNSUPPORTED_STYLE"
    assert result.effect_dispatched is None
    assert result.postcondition_verified is None


def test_semantic_checkbox_maps_unverified_postcondition_as_dispatched_failure() -> None:
    adapter = _FakeSemanticCheckboxAdapter(
        error="SEMANTIC_CHECKBOX_POSTCONDITION_NOT_VERIFIED"
    )
    action = SetSemanticCheckboxStateAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_CHECKBOX_POSTCONDITION_NOT_VERIFIED"
    assert result.effect_dispatched is True
    assert result.postcondition_verified is False


def test_catalog_builds_strict_semantic_checkbox_request() -> None:
    catalog = build_default_tool_catalog()
    token = "c" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="set_semantic_checkbox_state",
            arguments={
                "pid": 987,
                "title": " Janela ",
                "target_token": token,
                "observation_handle": handle,
                "control_token": "d" * 64,
                "role": "button",
                "name": " Ativar recurso ",
                "class_name": "Button",
                "control_id": None,
                "enabled": True,
                "checked": False,
            },
        )
    )

    assert request.action == "set_semantic_checkbox_state"
    assert request.arguments["title"] == "Janela"
    assert request.arguments["name"] == "Ativar recurso"
    assert request.arguments["checked"] is False
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item for item in catalog.definitions()
        if item.name == "set_semantic_checkbox_state"
    )
    assert set(definition.parameters["required"]) == set(
        definition.parameters["properties"]
    )
    assert definition.parameters["additionalProperties"] is False


def test_catalog_rejects_invalid_semantic_checkbox_rows_and_state() -> None:
    catalog = build_default_tool_catalog()
    token = "e" * 64
    base = {
        "pid": 987,
        "title": "Janela",
        "target_token": token,
        "observation_handle": build_window_observation_handle(token),
        "control_token": "f" * 64,
        "role": "button",
        "name": "Opção",
        "class_name": "Button",
        "control_id": 1,
        "enabled": True,
        "checked": True,
    }

    for changed in (
        {"control_token": "INVALID"},
        {"role": "label"},
        {"name": ""},
        {"class_name": "Static"},
        {"enabled": False},
        {"control_id": -1},
        {"checked": 1},
        {"checked": "true"},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="set_semantic_checkbox_state",
                    arguments={**base, **changed},
                )
            )


def test_semantic_checkbox_is_normal_window_capability_with_guidance() -> None:
    full = {item.name for item in build_default_tool_catalog().definitions()}
    assistant = {
        item.name for item in build_assistant_tool_catalog().definitions()
    }
    registry = set(build_action_registry().names())

    assert len(full) == 60
    assert len(assistant) == 44
    assert "set_semantic_checkbox_state" in full
    assert "set_semantic_checkbox_state" in assistant
    assert "set_semantic_checkbox_state" in registry
    assert (
        workflow_domain_for_action("set_semantic_checkbox_state")
        is WorkflowDomain.WINDOW
    )
    assert "set_semantic_checkbox_state" in _SYSTEM_INSTRUCTIONS
    assert "BS_AUTOCHECKBOX" in _SYSTEM_INSTRUCTIONS
    assert "BM_GETCHECK" in _SYSTEM_INSTRUCTIONS
