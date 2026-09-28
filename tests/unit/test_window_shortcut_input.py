from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PressShortcutAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeShortcutAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def press_shortcut(
        self,
        pid: int,
        title: str,
        target_token: str,
        shortcut: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, shortcut))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "shortcut": shortcut,
            "input_events_submitted": 4,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "target_activation_verified": True,
            "foreground_reacquired_before_input": True,
            "restored_from_minimized": False,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": "SendInput_CTRL_A",
            "clipboard_used": False,
            "shortcut_allowlist": ["CTRL_A"],
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_press_shortcut_requires_preview_guard() -> None:
    adapter = _FakeShortcutAdapter()
    action = PressShortcutAction(adapter)
    request = ActionRequest(
        action="press_shortcut",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "shortcut": "CTRL_A",
        },
    )

    assert action.risk is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "SHORTCUT_INPUT_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "PRESSIONAR ATALHO EM JANELA" in preview.text
    assert "Atalho: CTRL+A" in preview.text
    assert "Somente CTRL+A está permitido" in preview.text
    assert "área de transferência" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "CTRL_A")
    ]
    assert result.evidence["input_events_submitted"] == 4
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["content_effect_verified"] is False


def test_catalog_builds_ctrl_a_shortcut_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_shortcut",
            arguments={
                "pid": 4321,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "shortcut": "CTRL_A",
            },
        )
    )

    assert request.action == "press_shortcut"
    assert request.arguments == {
        "pid": 4321,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "shortcut": "CTRL_A",
    }


def test_catalog_rejects_unlisted_shortcuts() -> None:
    catalog = build_default_tool_catalog()

    for shortcut in ("CTRL_C", "CTRL_V", "ALT_F4"):
        try:
            catalog.build_action_request(
                ToolCall(
                    name="press_shortcut",
                    arguments={
                        "pid": 4321,
                        "title": "Bloco de Notas",
                        "target_token": "c" * 64,
                        "shortcut": shortcut,
                    },
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError(f"{shortcut} must remain blocked")
