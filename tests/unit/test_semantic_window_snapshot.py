from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import SemanticWindowSnapshotAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.core.window_observations import build_window_observation_handle
from theos.core.window_semantics import (
    build_semantic_control_token,
    is_semantic_control_token,
    semantic_name_allowed_for_class,
    semantic_role_for_class,
)


class _FakeSemanticAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def semantic_window_snapshot(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token))
        return {
            "pid": pid,
            "title": title,
            "target_token": target_token,
            "semantic_snapshot_version": 1,
            "semantic_source": "win32_native_child_controls",
            "observed_native_children": 3,
            "visible_native_controls": 2,
            "returned_controls": 2,
            "max_results": 32,
            "max_name_chars": 120,
            "text_values_collected": False,
            "raw_hwnd_exposed": False,
            "coordinate_action_dispatched": False,
            "controls": [
                {
                    "role": "button",
                    "name": "Salvar",
                    "class_name": "Button",
                    "control_id": 100,
                    "enabled": True,
                    "control_token": "b" * 64,
                },
                {
                    "role": "text_editor",
                    "name": None,
                    "class_name": "RichEditD2DPT",
                    "control_id": None,
                    "enabled": True,
                    "control_token": "c" * 64,
                },
            ],
        }


def test_semantic_role_classification_covers_native_control_families() -> None:
    assert semantic_role_for_class("Button") == "button"
    assert semantic_role_for_class("Static") == "label"
    assert semantic_role_for_class("Edit") == "text_editor"
    assert semantic_role_for_class("RichEditD2DPT") == "text_editor"
    assert semantic_role_for_class("ComboBoxEx32") == "combo_box"
    assert semantic_role_for_class("SysListView32") == "list"
    assert semantic_role_for_class("SysTreeView32") == "tree"
    assert semantic_role_for_class("UnknownWidget") == "native_control"


def test_semantic_name_policy_does_not_collect_edit_values() -> None:
    assert semantic_name_allowed_for_class("Button") is True
    assert semantic_name_allowed_for_class("Static") is True
    assert semantic_name_allowed_for_class("Edit") is False
    assert semantic_name_allowed_for_class("RichEditD2DPT") is False
    assert semantic_name_allowed_for_class("ComboBox") is False


def test_semantic_control_token_is_opaque_stable_and_child_specific() -> None:
    parent = "a" * 64
    first = build_semantic_control_token(
        parent,
        child_hwnd=101,
        pid=4321,
        class_name="Button",
        control_id=100,
    )
    same = build_semantic_control_token(
        parent,
        child_hwnd=101,
        pid=4321,
        class_name="Button",
        control_id=100,
    )
    other = build_semantic_control_token(
        parent,
        child_hwnd=202,
        pid=4321,
        class_name="Button",
        control_id=100,
    )

    assert is_semantic_control_token(first) is True
    assert first == same
    assert first != other
    assert is_semantic_control_token(first.upper()) is False


def test_semantic_snapshot_preview_is_confirmed_privacy_bounded_and_adapter_free() -> None:
    adapter = _FakeSemanticAdapter()
    action = SemanticWindowSnapshotAction(adapter)
    token = "d" * 64
    handle = build_window_observation_handle(token)
    request = ActionRequest(
        action="semantic_window_snapshot",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": token,
            "observation_handle": handle,
        },
    )

    assert action.risk is ActionRisk.CONFIRM
    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "CONTROLES SEMÂNTICOS NATIVOS" in preview.text
    assert "Valores de campos de texto" in preview.text
    assert "handles HWND brutos" in preview.text
    assert "32 controles" in preview.text
    assert adapter.calls == []


def test_semantic_snapshot_executes_with_fresh_observation_handle() -> None:
    adapter = _FakeSemanticAdapter()
    action = SemanticWindowSnapshotAction(adapter)
    token = "e" * 64
    handle = build_window_observation_handle(token)

    result = action.execute(
        ActionRequest(
            action="semantic_window_snapshot",
            arguments={
                "pid": 4321,
                "title": "Sem título - Bloco de Notas",
                "target_token": token,
                "observation_handle": handle,
            },
        )
    )

    assert result.success is True
    assert adapter.calls == [(4321, "Sem título - Bloco de Notas", token)]
    assert result.evidence["semantic_source"] == "win32_native_child_controls"
    assert result.evidence["text_values_collected"] is False
    assert result.evidence["raw_hwnd_exposed"] is False
    assert result.evidence["coordinate_action_dispatched"] is False
    assert "2 retornados" in result.message


def test_semantic_snapshot_rejects_expired_handle_before_adapter() -> None:
    adapter = _FakeSemanticAdapter()
    action = SemanticWindowSnapshotAction(adapter)
    token = "f" * 64
    expired = build_window_observation_handle(token, now=1)

    result = action.execute(
        ActionRequest(
            action="semantic_window_snapshot",
            arguments={
                "pid": 4321,
                "title": "Bloco de Notas",
                "target_token": token,
                "observation_handle": expired,
            },
        )
    )

    assert result.success is False
    assert result.error_code == "WINDOW_OBSERVATION_EXPIRED"
    assert adapter.calls == []


def test_catalog_builds_strict_semantic_snapshot_request() -> None:
    catalog = build_default_tool_catalog()
    token = "1" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="semantic_window_snapshot",
            arguments={
                "pid": 4321,
                "title": " Bloco de Notas ",
                "target_token": token,
                "observation_handle": handle,
            },
        )
    )

    assert request.action == "semantic_window_snapshot"
    assert request.arguments["title"] == "Bloco de Notas"
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item
        for item in catalog.definitions()
        if item.name == "semantic_window_snapshot"
    )
    schema = definition.parameters
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["observation_handle"]["type"] == "object"
    assert schema["additionalProperties"] is False


def test_catalog_rejects_missing_or_null_semantic_observation_handle() -> None:
    catalog = build_default_tool_catalog()
    token = "2" * 64

    for arguments in (
        {
            "pid": 4321,
            "title": "Bloco de Notas",
            "target_token": token,
        },
        {
            "pid": 4321,
            "title": "Bloco de Notas",
            "target_token": token,
            "observation_handle": None,
        },
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="semantic_window_snapshot",
                    arguments=arguments,
                )
            )
