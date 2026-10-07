from __future__ import annotations

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import SelectSemanticRadioButtonAction
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


class _FakeSemanticRadioAdapter:
    def __init__(
        self,
        *,
        error: str | None = None,
        dispatched: bool = True,
    ) -> None:
        self.error = error
        self.dispatched = dispatched
        self.calls: list[
            tuple[int, str, str, str, str, int | None]
        ] = []

    def select_semantic_radio_button(
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
            "radio_style": "BS_AUTORADIOBUTTON",
            "selected_before": not self.dispatched,
            "selected_after": True,
            "semantic_radio_click_dispatched": self.dispatched,
            "coordinate_action_dispatched": False,
            "cursor_moved": False,
            "keyboard_input_dispatched": False,
            "clipboard_used": False,
            "content_effect_verified": True,
            "radio_postcondition_verified": True,
            "radio_group_exclusivity_verified": False,
            "raw_hwnd_exposed": False,
        }


def _request() -> ActionRequest:
    token = "a" * 64
    return ActionRequest(
        action="select_semantic_radio_button",
        arguments={
            "pid": 4321,
            "title": "Janela de teste",
            "target_token": token,
            "observation_handle": build_window_observation_handle(token),
            "control_token": "b" * 64,
            "role": "button",
            "name": "Modo avançado",
            "class_name": "Button",
            "control_id": 100,
            "enabled": True,
        },
    )


def _approved_request(
    action: SelectSemanticRadioButtonAction,
) -> ActionRequest:
    request = _request()
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)
    return request


def test_semantic_radio_preview_binds_exact_control() -> None:
    adapter = _FakeSemanticRadioAdapter()
    action = SelectSemanticRadioButtonAction(adapter)
    preview = action.confirmation_preview(_request())

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "SELECIONAR RADIO BUTTON SEMÂNTICO NATIVO" in preview.text
    assert "Modo avançado" in preview.text
    assert "BS_AUTORADIOBUTTON" in preview.text
    assert "BM_GETCHECK" in preview.text
    assert "BM_CLICK" in preview.text
    assert len(preview.execution_guard) == 7
    assert adapter.calls == []


def test_semantic_radio_preview_blocks_non_button_row() -> None:
    adapter = _FakeSemanticRadioAdapter()
    action = SelectSemanticRadioButtonAction(adapter)
    request = _request()
    request.arguments["class_name"] = "Static"

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_radio_execute_requires_approved_preview_guard() -> None:
    adapter = _FakeSemanticRadioAdapter()
    action = SelectSemanticRadioButtonAction(adapter)

    result = action.execute(_request())

    assert result.success is False
    assert result.error_code == "SEMANTIC_RADIO_PREVIEW_REQUIRED"
    assert adapter.calls == []


def test_semantic_radio_executes_exact_approved_control_and_verifies() -> None:
    adapter = _FakeSemanticRadioAdapter()
    action = SelectSemanticRadioButtonAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["semantic_radio_click_dispatched"] is True
    assert result.evidence["content_effect_verified"] is True
    assert result.evidence["radio_postcondition_verified"] is True
    assert result.evidence["selected_after"] is True
    assert result.evidence["radio_group_exclusivity_verified"] is False
    assert result.evidence["coordinate_action_dispatched"] is False
    assert result.evidence["keyboard_input_dispatched"] is False
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["raw_hwnd_exposed"] is False


def test_semantic_radio_successful_noop_is_verified_without_dispatch() -> None:
    adapter = _FakeSemanticRadioAdapter(dispatched=False)
    action = SelectSemanticRadioButtonAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is True
    assert result.effect_dispatched is False
    assert result.postcondition_verified is True
    assert result.evidence["semantic_radio_click_dispatched"] is False
    assert result.evidence["selected_before"] is True
    assert result.evidence["selected_after"] is True


def test_semantic_radio_rejects_expired_window_observation() -> None:
    adapter = _FakeSemanticRadioAdapter()
    action = SelectSemanticRadioButtonAction(adapter)
    request = _request()
    request.arguments["observation_handle"] = build_window_observation_handle(
        "a" * 64,
        now=1,
    )

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_radio_maps_unsupported_style_without_dispatch_claim() -> None:
    adapter = _FakeSemanticRadioAdapter(
        error="SEMANTIC_RADIO_UNSUPPORTED_STYLE"
    )
    action = SelectSemanticRadioButtonAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_RADIO_UNSUPPORTED_STYLE"
    assert result.effect_dispatched is None
    assert result.postcondition_verified is None


def test_semantic_radio_maps_unverified_postcondition_as_dispatched_failure() -> None:
    adapter = _FakeSemanticRadioAdapter(
        error="SEMANTIC_RADIO_POSTCONDITION_NOT_VERIFIED"
    )
    action = SelectSemanticRadioButtonAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_RADIO_POSTCONDITION_NOT_VERIFIED"
    assert result.effect_dispatched is True
    assert result.postcondition_verified is False


def test_catalog_builds_strict_semantic_radio_request() -> None:
    catalog = build_default_tool_catalog()
    token = "c" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="select_semantic_radio_button",
            arguments={
                "pid": 987,
                "title": " Janela ",
                "target_token": token,
                "observation_handle": handle,
                "control_token": "d" * 64,
                "role": "button",
                "name": " Opção A ",
                "class_name": "Button",
                "control_id": None,
                "enabled": True,
            },
        )
    )

    assert request.action == "select_semantic_radio_button"
    assert request.arguments["title"] == "Janela"
    assert request.arguments["name"] == "Opção A"
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item for item in catalog.definitions()
        if item.name == "select_semantic_radio_button"
    )
    assert set(definition.parameters["required"]) == set(
        definition.parameters["properties"]
    )
    assert definition.parameters["additionalProperties"] is False


def test_catalog_rejects_invalid_semantic_radio_rows() -> None:
    catalog = build_default_tool_catalog()
    token = "e" * 64
    base = {
        "pid": 987,
        "title": "Janela",
        "target_token": token,
        "observation_handle": build_window_observation_handle(token),
        "control_token": "f" * 64,
        "role": "button",
        "name": "Opção A",
        "class_name": "Button",
        "control_id": 1,
        "enabled": True,
    }

    for changed in (
        {"control_token": "INVALID"},
        {"role": "list"},
        {"name": " "},
        {"class_name": "Static"},
        {"enabled": False},
        {"control_id": -1},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="select_semantic_radio_button",
                    arguments={**base, **changed},
                )
            )


def test_semantic_radio_is_normal_window_capability_with_guidance() -> None:
    full = {item.name for item in build_default_tool_catalog().definitions()}
    assistant = {
        item.name for item in build_assistant_tool_catalog().definitions()
    }
    registry = set(build_action_registry().names())

    assert len(full) == 61
    assert len(assistant) == 45
    assert "select_semantic_radio_button" in full
    assert "select_semantic_radio_button" in assistant
    assert "select_semantic_radio_button" in registry
    assert (
        workflow_domain_for_action("select_semantic_radio_button")
        is WorkflowDomain.WINDOW
    )
    assert "select_semantic_radio_button" in _SYSTEM_INSTRUCTIONS
    assert "BS_AUTORADIOBUTTON" in _SYSTEM_INSTRUCTIONS
    assert "BM_GETCHECK" in _SYSTEM_INSTRUCTIONS
    assert "BM_CLICK" in _SYSTEM_INSTRUCTIONS
