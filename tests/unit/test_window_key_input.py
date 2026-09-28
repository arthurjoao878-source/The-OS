from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PressKeyAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeKeyInputAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def press_key(self, pid: int, title: str, key: str) -> dict[str, object]:
        self.calls.append((pid, title, key))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "key": key,
            "input_events_submitted": 2,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": "SendInput_VK_RETURN",
            "clipboard_used": False,
            "key_allowlist": ["ENTER"],
            "title_match": "bounded_title_exact",
        }


def test_press_key_requires_preview_guard_and_uses_enter_only() -> None:
    adapter = _FakeKeyInputAdapter()
    action = PressKeyAction(adapter)
    request = ActionRequest(
        action="press_key",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "key": "ENTER",
        },
    )

    assert action.risk is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "KEY_INPUT_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "PRESSIONAR TECLA EM JANELA" in preview.text
    assert "Tecla: ENTER" in preview.text
    assert "pode confirmar, enviar ou ativar" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [(4321, "Sem título - Bloco de Notas", "ENTER")]
    assert result.evidence["input_submission_verified"] is True
    assert result.evidence["content_effect_verified"] is False
    assert result.evidence["key_allowlist"] == ["ENTER"]


def test_catalog_builds_press_key_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_key",
            arguments={
                "pid": 4321,
                "title": " Sem título - Bloco de Notas ",
                "key": "ENTER",
            },
        )
    )

    assert request.action == "press_key"
    assert request.arguments == {
        "pid": 4321,
        "title": "Sem título - Bloco de Notas",
        "key": "ENTER",
    }


def test_catalog_rejects_non_allowlisted_key() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="press_key",
                arguments={
                    "pid": 4321,
                    "title": "Bloco de Notas",
                    "key": "TAB",
                },
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("non-allowlisted key must be rejected")
