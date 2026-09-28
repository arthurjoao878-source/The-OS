from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PressKeyAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeKeyInputAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def press_key(
        self,
        pid: int,
        title: str,
        target_token: str,
        key: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, key))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
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
            "input_method": f"SendInput_VK_{key}",
            "clipboard_used": False,
            "key_allowlist": ["ENTER", "ESCAPE", "TAB"],
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_press_key_requires_preview_guard_for_allowlisted_key() -> None:
    adapter = _FakeKeyInputAdapter()
    action = PressKeyAction(adapter)
    request = ActionRequest(
        action="press_key",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
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
    assert "ENTER pode confirmar/enviar" in preview.text
    assert "Alvo opaco: aaaaaaaaaaaa..." in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "ENTER")
    ]
    assert result.evidence["input_submission_verified"] is True
    assert result.evidence["content_effect_verified"] is False
    assert result.evidence["key_allowlist"] == ["ENTER", "ESCAPE", "TAB"]


def test_catalog_builds_press_key_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_key",
            arguments={
                "pid": 4321,
                "title": " Sem título - Bloco de Notas ",
                "target_token": "a" * 64,
                "key": "ENTER",
            },
        )
    )

    assert request.action == "press_key"
    assert request.arguments == {
        "pid": 4321,
        "title": "Sem título - Bloco de Notas",
        "target_token": "a" * 64,
        "key": "ENTER",
    }


def test_catalog_accepts_escape_and_tab() -> None:
    catalog = build_default_tool_catalog()

    for key in ("ESCAPE", "TAB"):
        request = catalog.build_action_request(
            ToolCall(
                name="press_key",
                arguments={
                    "pid": 4321,
                    "title": "Bloco de Notas",
                    "target_token": "b" * 64,
                    "key": key,
                },
            )
        )
        assert request.arguments["key"] == key


def test_catalog_rejects_non_allowlisted_key() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="press_key",
                arguments={
                    "pid": 4321,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "key": "DELETE",
                },
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("non-allowlisted key must be rejected")


def test_catalog_rejects_invalid_target_token() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="press_key",
                arguments={
                    "pid": 4321,
                    "title": "Bloco de Notas",
                    "target_token": "not-a-token",
                    "key": "ESCAPE",
                },
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid target token must be rejected")


def test_escape_preview_guard_executes_exact_escape() -> None:
    adapter = _FakeKeyInputAdapter()
    action = PressKeyAction(adapter)
    request = ActionRequest(
        action="press_key",
        arguments={
            "pid": 8765,
            "title": "Calculadora",
            "target_token": "d" * 64,
            "key": "ESCAPE",
        },
    )

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Tecla: ESCAPE" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (8765, "Calculadora", "d" * 64, "ESCAPE")
    ]
    assert result.evidence["input_method"] == "SendInput_VK_ESCAPE"
