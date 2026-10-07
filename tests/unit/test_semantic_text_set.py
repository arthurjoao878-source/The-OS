from __future__ import annotations

import hashlib

import pytest

from theos.bootstrap import build_action_registry
from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import SetSemanticTextAction
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


class _FakeSemanticTextAdapter:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[
            tuple[int, str, str, str, int | None, str]
        ] = []

    def set_semantic_text(
        self,
        pid: int,
        title: str,
        target_token: str,
        control_token: str,
        control_id: int | None,
        text: str,
    ) -> dict[str, object]:
        self.calls.append(
            (pid, title, target_token, control_token, control_id, text)
        )
        if self.error is not None:
            raise RuntimeError(self.error)
        return {
            "pid": pid,
            "title": title,
            "target_token": target_token,
            "control_token": control_token,
            "role": "text_editor",
            "class_name": "Edit",
            "control_id": control_id,
            "text_chars": len(text),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "semantic_text_set_dispatched": True,
            "coordinate_action_dispatched": False,
            "cursor_moved": False,
            "keyboard_input_dispatched": False,
            "clipboard_used": False,
            "content_effect_verified": True,
            "text_postcondition_verified": True,
            "text_value_returned_in_evidence": False,
            "raw_hwnd_exposed": False,
        }


def _request() -> ActionRequest:
    token = "a" * 64
    return ActionRequest(
        action="set_semantic_text",
        arguments={
            "pid": 4321,
            "title": "Janela de teste",
            "target_token": token,
            "observation_handle": build_window_observation_handle(token),
            "control_token": "b" * 64,
            "role": "text_editor",
            "class_name": "Edit",
            "control_id": 100,
            "enabled": True,
            "text": "Texto M105",
        },
    )


def _approved_request(action: SetSemanticTextAction) -> ActionRequest:
    request = _request()
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)
    return request


def test_semantic_text_preview_binds_exact_control_and_text() -> None:
    adapter = _FakeSemanticTextAdapter()
    action = SetSemanticTextAction(adapter)
    preview = action.confirmation_preview(_request())

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "SUBSTITUIR TEXTO DE EDIT SEMÂNTICO NATIVO" in preview.text
    assert "Texto M105" in preview.text
    assert "WM_SETTEXT" in preview.text
    assert "password" in preview.text
    assert "read-only" in preview.text
    assert len(preview.execution_guard) == 7
    assert adapter.calls == []


def test_semantic_text_preview_blocks_non_edit_row() -> None:
    adapter = _FakeSemanticTextAdapter()
    action = SetSemanticTextAction(adapter)
    request = _request()
    request.arguments["class_name"] = "RichEdit20W"

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_text_execute_requires_approved_preview_guard() -> None:
    adapter = _FakeSemanticTextAdapter()
    action = SetSemanticTextAction(adapter)

    result = action.execute(_request())

    assert result.success is False
    assert result.error_code == "SEMANTIC_TEXT_PREVIEW_REQUIRED"
    assert adapter.calls == []


def test_semantic_text_executes_exact_approved_edit_and_verifies() -> None:
    adapter = _FakeSemanticTextAdapter()
    action = SetSemanticTextAction(adapter)

    result = action.execute(_approved_request(action))

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["semantic_text_set_dispatched"] is True
    assert result.evidence["content_effect_verified"] is True
    assert result.evidence["text_postcondition_verified"] is True
    assert result.evidence["coordinate_action_dispatched"] is False
    assert result.evidence["keyboard_input_dispatched"] is False
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["text_value_returned_in_evidence"] is False
    assert "text" not in result.evidence


def test_semantic_text_rejects_expired_window_observation() -> None:
    adapter = _FakeSemanticTextAdapter()
    action = SetSemanticTextAction(adapter)
    request = _request()
    request.arguments["observation_handle"] = build_window_observation_handle(
        "a" * 64,
        now=1,
    )

    assert action.confirmation_preview(request).allowed is False
    assert adapter.calls == []


def test_semantic_text_maps_password_edit_without_dispatch_claim() -> None:
    adapter = _FakeSemanticTextAdapter(
        error="SEMANTIC_TEXT_PASSWORD_BLOCKED"
    )
    result = SetSemanticTextAction(adapter).execute(
        _approved_request(SetSemanticTextAction(adapter))
    )

    assert result.success is False
    assert result.error_code == "SEMANTIC_TEXT_PASSWORD_BLOCKED"
    assert result.effect_dispatched is None
    assert result.postcondition_verified is None


def test_semantic_text_maps_read_only_edit_without_dispatch_claim() -> None:
    adapter = _FakeSemanticTextAdapter(
        error="SEMANTIC_TEXT_READ_ONLY_BLOCKED"
    )
    action = SetSemanticTextAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_TEXT_READ_ONLY_BLOCKED"
    assert result.effect_dispatched is None
    assert result.postcondition_verified is None


def test_semantic_text_maps_unverified_postcondition_as_dispatched_failure() -> None:
    adapter = _FakeSemanticTextAdapter(
        error="SEMANTIC_TEXT_POSTCONDITION_NOT_VERIFIED"
    )
    action = SetSemanticTextAction(adapter)
    result = action.execute(_approved_request(action))

    assert result.success is False
    assert result.error_code == "SEMANTIC_TEXT_POSTCONDITION_NOT_VERIFIED"
    assert result.effect_dispatched is True
    assert result.postcondition_verified is False


def test_catalog_builds_strict_semantic_text_request() -> None:
    catalog = build_default_tool_catalog()
    token = "c" * 64
    handle = build_window_observation_handle(token)

    request = catalog.build_action_request(
        ToolCall(
            name="set_semantic_text",
            arguments={
                "pid": 987,
                "title": " Janela ",
                "target_token": token,
                "observation_handle": handle,
                "control_token": "d" * 64,
                "role": "text_editor",
                "class_name": "Edit",
                "control_id": None,
                "enabled": True,
                "text": "Valor exato",
            },
        )
    )

    assert request.action == "set_semantic_text"
    assert request.arguments["title"] == "Janela"
    assert request.arguments["text"] == "Valor exato"
    assert request.arguments["observation_handle"] == handle

    definition = next(
        item for item in catalog.definitions()
        if item.name == "set_semantic_text"
    )
    assert set(definition.parameters["required"]) == set(
        definition.parameters["properties"]
    )
    assert definition.parameters["additionalProperties"] is False


def test_catalog_rejects_invalid_semantic_text_rows_and_text() -> None:
    catalog = build_default_tool_catalog()
    token = "e" * 64
    base = {
        "pid": 987,
        "title": "Janela",
        "target_token": token,
        "observation_handle": build_window_observation_handle(token),
        "control_token": "f" * 64,
        "role": "text_editor",
        "class_name": "Edit",
        "control_id": 1,
        "enabled": True,
        "text": "Valor",
    }

    for changed in (
        {"control_token": "INVALID"},
        {"role": "button"},
        {"class_name": "RichEdit20W"},
        {"enabled": False},
        {"control_id": -1},
        {"text": ""},
        {"text": "linha\nquebrada"},
        {"text": "x" * 513},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="set_semantic_text",
                    arguments={**base, **changed},
                )
            )


def test_semantic_text_is_normal_window_capability_with_guidance() -> None:
    full = {item.name for item in build_default_tool_catalog().definitions()}
    assistant = {
        item.name for item in build_assistant_tool_catalog().definitions()
    }
    registry = set(build_action_registry().names())

    assert len(full) == 58
    assert len(assistant) == 42
    assert "set_semantic_text" in full
    assert "set_semantic_text" in assistant
    assert "set_semantic_text" in registry
    assert (
        workflow_domain_for_action("set_semantic_text")
        is WorkflowDomain.WINDOW
    )
    assert "set_semantic_text" in _SYSTEM_INSTRUCTIONS
    assert "password" in _SYSTEM_INSTRUCTIONS
    assert "read-only" in _SYSTEM_INSTRUCTIONS
