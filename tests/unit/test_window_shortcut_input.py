from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PressShortcutAction
from theos.core.keyboard_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    format_window_shortcut_allowlist_pt,
    get_window_shortcut_spec,
)
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
        shortcut_spec = get_window_shortcut_spec(shortcut)
        assert shortcut_spec is not None
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
            "input_method": f"SendInput_{shortcut}",
            "clipboard_used": shortcut_spec.clipboard_used,
            "clipboard_api_used_by_theos": False,
            "clipboard_effect_expected": shortcut_spec.clipboard_effect_expected,
            "clipboard_effect_verified": False,
            "clipboard_input_expected": shortcut_spec.clipboard_input_expected,
            "clipboard_content_inspected_by_theos": False,
            "clipboard_content_provider_visible": False,
            "content_mutation_expected": shortcut_spec.content_mutation_expected,
            "shortcut_allowlist": list(ALLOWED_WINDOW_SHORTCUTS),
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
    assert (
        f"Somente {format_window_shortcut_allowlist_pt()} estão permitidos"
        in preview.text
    )
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

    for shortcut in ("CTRL_A_EXTRA", "CTRL_ALT_DELETE", "SHIFT_F13"):
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

def test_catalog_builds_ctrl_c_shortcut_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_shortcut",
            arguments={
                "pid": 4321,
                "title": "Bloco de Notas",
                "target_token": "d" * 64,
                "shortcut": "CTRL_C",
            },
        )
    )

    assert request.action == "press_shortcut"
    assert request.arguments["shortcut"] == "CTRL_C"


def test_ctrl_c_preview_guard_executes_exact_copy_shortcut() -> None:
    adapter = _FakeShortcutAdapter()
    action = PressShortcutAction(adapter)
    request = ActionRequest(
        action="press_shortcut",
        arguments={
            "pid": 8765,
            "title": "Sem título - Bloco de Notas",
            "target_token": "e" * 64,
            "shortcut": "CTRL_C",
        },
    )

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Atalho: CTRL+C" in preview.text
    assert "ATENÇÃO: CTRL+C pode substituir" in preview.text
    assert "não lê a área de transferência" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (8765, "Sem título - Bloco de Notas", "e" * 64, "CTRL_C")
    ]
    assert result.evidence["input_method"] == "SendInput_CTRL_C"
    assert result.evidence["clipboard_api_used_by_theos"] is False
    assert result.evidence["clipboard_effect_expected"] is True
    assert result.evidence["clipboard_effect_verified"] is False

def test_catalog_builds_ctrl_x_shortcut_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_shortcut",
            arguments={
                "pid": 4321,
                "title": "Bloco de Notas",
                "target_token": "f" * 64,
                "shortcut": "CTRL_X",
            },
        )
    )

    assert request.action == "press_shortcut"
    assert request.arguments["shortcut"] == "CTRL_X"


def test_ctrl_x_preview_guard_and_risk_are_destructive() -> None:
    adapter = _FakeShortcutAdapter()
    action = PressShortcutAction(adapter)
    request = ActionRequest(
        action="press_shortcut",
        arguments={
            "pid": 8765,
            "title": "Sem título - Bloco de Notas",
            "target_token": "1" * 64,
            "shortcut": "CTRL_X",
        },
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Atalho: CTRL+X" in preview.text
    assert "ATENÇÃO: CTRL+X pode remover" in preview.text
    assert "área de transferência" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (8765, "Sem título - Bloco de Notas", "1" * 64, "CTRL_X")
    ]
    assert result.evidence["input_method"] == "SendInput_CTRL_X"
    assert result.evidence["clipboard_api_used_by_theos"] is False
    assert result.evidence["clipboard_effect_expected"] is True
    assert result.evidence["clipboard_effect_verified"] is False
    assert result.evidence["content_mutation_expected"] is True


def test_ctrl_a_and_ctrl_c_risk_remain_confirm() -> None:
    for shortcut in ("CTRL_A", "CTRL_C"):
        request = ActionRequest(
            action="press_shortcut",
            arguments={
                "pid": 8765,
                "title": "Sem título - Bloco de Notas",
                "target_token": "2" * 64,
                "shortcut": shortcut,
            },
        )
        assert PressShortcutAction.risk_for(request) is ActionRisk.CONFIRM

def test_catalog_builds_ctrl_v_shortcut_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_shortcut",
            arguments={
                "pid": 4321,
                "title": "Bloco de Notas",
                "target_token": "3" * 64,
                "shortcut": "CTRL_V",
            },
        )
    )

    assert request.action == "press_shortcut"
    assert request.arguments["shortcut"] == "CTRL_V"


def test_ctrl_v_preview_guard_and_risk_are_privileged() -> None:
    adapter = _FakeShortcutAdapter()
    action = PressShortcutAction(adapter)
    request = ActionRequest(
        action="press_shortcut",
        arguments={
            "pid": 8765,
            "title": "Sem título - Bloco de Notas",
            "target_token": "4" * 64,
            "shortcut": "CTRL_V",
        },
    )

    assert action.risk_for(request) is ActionRisk.PRIVILEGED

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Atalho: CTRL+V" in preview.text
    assert "PRIVILEGIADO: CTRL+V pode inserir" in preview.text
    assert "pode conter dados sensíveis" in preview.text
    assert "não mostra ao provedor" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (8765, "Sem título - Bloco de Notas", "4" * 64, "CTRL_V")
    ]
    assert result.evidence["input_method"] == "SendInput_CTRL_V"
    assert result.evidence["clipboard_used"] is True
    assert result.evidence["clipboard_api_used_by_theos"] is False
    assert result.evidence["clipboard_input_expected"] is True
    assert result.evidence["clipboard_content_inspected_by_theos"] is False
    assert result.evidence["clipboard_content_provider_visible"] is False
    assert result.evidence["content_mutation_expected"] is True
    assert result.evidence["content_effect_verified"] is False

def test_catalog_builds_ctrl_z_shortcut_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="press_shortcut",
            arguments={
                "pid": 4321,
                "title": "Bloco de Notas",
                "target_token": "5" * 64,
                "shortcut": "CTRL_Z",
            },
        )
    )

    assert request.action == "press_shortcut"
    assert request.arguments["shortcut"] == "CTRL_Z"


def test_ctrl_z_preview_guard_and_risk_are_destructive() -> None:
    adapter = _FakeShortcutAdapter()
    action = PressShortcutAction(adapter)
    request = ActionRequest(
        action="press_shortcut",
        arguments={
            "pid": 8765,
            "title": "Sem título - Bloco de Notas",
            "target_token": "6" * 64,
            "shortcut": "CTRL_Z",
        },
    )

    assert action.risk_for(request) is ActionRisk.DESTRUCTIVE

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Atalho: CTRL+Z" in preview.text
    assert "ATENÇÃO: CTRL+Z pode desfazer" in preview.text
    assert "não inspeciona o histórico de desfazer" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (8765, "Sem título - Bloco de Notas", "6" * 64, "CTRL_Z")
    ]
    assert result.evidence["input_method"] == "SendInput_CTRL_Z"
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["clipboard_api_used_by_theos"] is False
    assert result.evidence["content_mutation_expected"] is True
    assert result.evidence["content_effect_verified"] is False
