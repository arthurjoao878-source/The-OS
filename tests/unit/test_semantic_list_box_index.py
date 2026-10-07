from __future__ import annotations

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import SetSemanticListBoxIndexAction
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


class _FakeSemanticListBoxAdapter:
    def __init__(
        self,
        *,
        error: str | None = None,
        dispatched: bool = True,
    ) -> None:
        self.error = error
        self.dispatched = dispatched
        self.calls: list[
            tuple[int, str, str, str, int | None, int]
        ] = []

    def set_semantic_list_box_index(
        self,
        pid: int,
        title: str,
        target_token: str,
        control_token: str,
        control_id: int | None,
        selected_index: int,
    ) -> dict[str, object]:
        self.calls.append(
            (
                pid,
                title,
                target_token,
                control_token,
                control_id,
                selected_index,
            )
        )
        if self.error is not None:
            raise RuntimeError(self.error)
        before = 0 if self.dispatched else selected_index
        return {
            "pid": pid,
            "title": title,
            "target_token": target_token,
            "control_token": control_token,
            "role": "list",
            "class_name": "ListBox",
            "control_id": control_id,
            "item_count": 4,
            "single_selection": True,
            "selected_index_before": before,
            "selected_index_after": selected_index,
            "desired_index": selected_index,
            "semantic_list_box_selection_dispatched": self.dispatched,
            "list_item_text_collected": False,
            "coordinate_action_dispatched": False,
            "cursor_moved": False,
            "keyboard_input_dispatched": False,
            "clipboard_used": False,
            "content_effect_verified": True,
            "list_box_postcondition_verified": True,
            "application_selection_notification_verified": False,
            "raw_hwnd_exposed": False,
        }


def _request(*, selected_index: int = 2) -> ActionRequest:
    token = "a" * 64
    return ActionRequest(
        action="set_semantic_list_box_index",
        arguments={
            "pid": 4321,
            "title": "Janela de teste",
            "target_token": token,
            "observation_handle": build_window_observation_handle(token),
            "control_token": "b" * 64,
            "role": "list",
            "class_name": "ListBox",
            "control_id": 100,
            "enabled": True,
            "selected_index": selected_index,
        },
    )


def _approved_request(
    action: SetSemanticListBoxIndexAction,
    *,
    selected_index: int = 2,
) -> ActionRequest:
    request = _request(selected_index=selected_index)
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)
    return request


def test_semantic_list_box_preview_binds_exact_control_and_index() -> None:
    adapter = _FakeSemanticListBoxAdapter()
    action = SetSemanticListBoxIndexAction(adapter)
    preview = action.confirmation_preview(_request())

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "DEFINIR ÍNDICE DE LISTBOX SEMÂNTICO NATIVO" in preview.text
    assert "LB_GETCOUNT" in preview.text
    assert "LB_GETCURSEL" in preview.text
    assert "LB_SETCURSEL" in preview.text
    assert "base zero" in preview.text
    assert len(preview.execution_guard) == 7
    assert adapter.calls == []


def test_semantic_list_box_preview_blocks_non_list_box_row() -> None:
    adapter = _FakeSemanticListBoxAdapter()
    action = SetSemanticListBoxIndexAction(adapter)
    request = _request()
    request.arguments["class_name"] = "SysListView32"

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_list_box_execute_requires_approved_preview_guard() -> None:
    adapter = _FakeSemanticListBoxAdapter()
    action = SetSemanticListBoxIndexAction(adapter)

    result = action.execute(_request())

    assert result.success is False
    assert result.error_code == "SEMANTIC_LIST_BOX_PREVIEW_REQUIRED"
    assert adapter.calls == []


def test_semantic_list_box_executes_exact_approved_index_and_verifies() -> None:
    adapter = _FakeSemanticListBoxAdapter()
    action = SetSemanticListBoxIndexAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["semantic_list_box_selection_dispatched"] is True
    assert result.evidence["content_effect_verified"] is True
    assert result.evidence["list_box_postcondition_verified"] is True
    assert result.evidence["desired_index"] == 2
    assert result.evidence["selected_index_after"] == 2
    assert result.evidence["list_item_text_collected"] is False
    assert result.evidence["application_selection_notification_verified"] is False
    assert result.evidence["coordinate_action_dispatched"] is False
    assert result.evidence["keyboard_input_dispatched"] is False
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["raw_hwnd_exposed"] is False


def test_semantic_list_box_successful_noop_is_verified_without_dispatch() -> None:
    adapter = _FakeSemanticListBoxAdapter(dispatched=False)
    action = SetSemanticListBoxIndexAction(adapter)

    result = action.execute(_approved_request(action, selected_index=1))

    assert result.success is True
    assert result.effect_dispatched is False
    assert result.postcondition_verified is True
    assert result.evidence["semantic_list_box_selection_dispatched"] is False
    assert result.evidence["desired_index"] == 1
    assert result.evidence["selected_index_before"] == 1
    assert result.evidence["selected_index_after"] == 1


def test_semantic_list_box_rejects_expired_window_observation() -> None:
    adapter = _FakeSemanticListBoxAdapter()
    action = SetSemanticListBoxIndexAction(adapter)
    request = _request()
    request.arguments["observation_handle"] = build_window_observation_handle(
        "a" * 64,
        now=1,
    )

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_list_box_maps_unsupported_multiselect_without_dispatch_claim() -> None:
    adapter = _FakeSemanticListBoxAdapter(
        error="SEMANTIC_LIST_BOX_UNSUPPORTED_MULTISELECT"
    )
    action = SetSemanticListBoxIndexAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_LIST_BOX_UNSUPPORTED_MULTISELECT"
    assert result.effect_dispatched is None
    assert result.postcondition_verified is None


def test_semantic_list_box_maps_unverified_postcondition_as_dispatched_failure() -> None:
    adapter = _FakeSemanticListBoxAdapter(
        error="SEMANTIC_LIST_BOX_POSTCONDITION_NOT_VERIFIED"
    )
    action = SetSemanticListBoxIndexAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_LIST_BOX_POSTCONDITION_NOT_VERIFIED"
    assert result.effect_dispatched is True
    assert result.postcondition_verified is False


def test_catalog_builds_strict_semantic_list_box_request() -> None:
    catalog = build_default_tool_catalog()
    token = "c" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="set_semantic_list_box_index",
            arguments={
                "pid": 987,
                "title": " Janela ",
                "target_token": token,
                "observation_handle": handle,
                "control_token": "d" * 64,
                "role": "list",
                "class_name": "ListBox",
                "control_id": None,
                "enabled": True,
                "selected_index": 3,
            },
        )
    )

    assert request.action == "set_semantic_list_box_index"
    assert request.arguments["title"] == "Janela"
    assert request.arguments["selected_index"] == 3
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item for item in catalog.definitions()
        if item.name == "set_semantic_list_box_index"
    )
    assert set(definition.parameters["required"]) == set(
        definition.parameters["properties"]
    )
    assert definition.parameters["additionalProperties"] is False


def test_catalog_rejects_invalid_semantic_list_box_rows_and_index() -> None:
    catalog = build_default_tool_catalog()
    token = "e" * 64
    base = {
        "pid": 987,
        "title": "Janela",
        "target_token": token,
        "observation_handle": build_window_observation_handle(token),
        "control_token": "f" * 64,
        "role": "list",
        "class_name": "ListBox",
        "control_id": 1,
        "enabled": True,
        "selected_index": 1,
    }

    for changed in (
        {"control_token": "INVALID"},
        {"role": "combo_box"},
        {"class_name": "SysListView32"},
        {"enabled": False},
        {"control_id": -1},
        {"selected_index": -1},
        {"selected_index": True},
        {"selected_index": "1"},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="set_semantic_list_box_index",
                    arguments={**base, **changed},
                )
            )


def test_semantic_list_box_is_normal_window_capability_with_guidance() -> None:
    full = {item.name for item in build_default_tool_catalog().definitions()}
    assistant = {
        item.name for item in build_assistant_tool_catalog().definitions()
    }
    registry = set(build_action_registry().names())

    assert len(full) == 60
    assert len(assistant) == 44
    assert "set_semantic_list_box_index" in full
    assert "set_semantic_list_box_index" in assistant
    assert "set_semantic_list_box_index" in registry
    assert (
        workflow_domain_for_action("set_semantic_list_box_index")
        is WorkflowDomain.WINDOW
    )
    assert "set_semantic_list_box_index" in _SYSTEM_INSTRUCTIONS
    assert "LB_GETCOUNT" in _SYSTEM_INSTRUCTIONS
    assert "LB_GETCURSEL" in _SYSTEM_INSTRUCTIONS
    assert "LB_SETCURSEL" in _SYSTEM_INSTRUCTIONS
