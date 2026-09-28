from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import TypeTextAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeTextInputAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def type_text(
        self,
        pid: int,
        title: str,
        target_token: str,
        text: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, text))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "text_chars": len(text),
            "utf16_units": len(text),
            "input_events_submitted": len(text) * 2,
            "foreground_verified_before": True,
            "foreground_verified_after": True,
            "input_submission_verified": True,
            "content_effect_verified": False,
            "verification": "sendinput_count_and_foreground_only",
            "input_method": "SendInput_KEYEVENTF_UNICODE",
            "clipboard_used": False,
            "special_keys_used": False,
            "control_characters_allowed": False,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_type_text_requires_preview_guard_and_preserves_literal_text() -> None:
    adapter = _FakeTextInputAdapter()
    action = TypeTextAction(adapter)
    request = ActionRequest(
        action="type_text",
        arguments={
            "pid": 4321,
            "title": "M28-LIVE.txt - Bloco de Notas",
            "target_token": "a" * 64,
            "text": "Olá, LYRA 123!",
        },
    )

    assert action.risk is ActionRisk.CONFIRM

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "TEXT_INPUT_PREVIEW_REQUIRED"
    assert adapter.calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "DIGITAR TEXTO EM JANELA" in preview.text
    assert "Alvo opaco: aaaaaaaaaaaa..." in preview.text
    assert "Olá, LYRA 123!" in preview.text
    assert "janela exata aprovada pelo token opaco" in preview.text
    assert adapter.calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (
            4321,
            "M28-LIVE.txt - Bloco de Notas",
            "a" * 64,
            "Olá, LYRA 123!",
        )
    ]
    assert result.evidence["input_submission_verified"] is True
    assert result.evidence["content_effect_verified"] is False
    assert result.evidence["clipboard_used"] is False
    assert result.evidence["special_keys_used"] is False
    assert result.evidence["title_match"] == (
        "pid_bounded_title_and_opaque_token_exact"
    )


def test_catalog_builds_type_text_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="type_text",
            arguments={
                "pid": 4321,
                "title": " M28-LIVE.txt - Bloco de Notas ",
                "target_token": "b" * 64,
                "text": "Texto literal",
            },
        )
    )

    assert request.action == "type_text"
    assert request.arguments == {
        "pid": 4321,
        "title": "M28-LIVE.txt - Bloco de Notas",
        "target_token": "b" * 64,
        "text": "Texto literal",
    }


def test_catalog_rejects_invalid_type_text_target_token() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="type_text",
                arguments={
                    "pid": 4321,
                    "title": "Bloco de Notas",
                    "target_token": "not-a-token",
                    "text": "Texto",
                },
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid target token must be rejected")


def test_catalog_rejects_control_characters_and_oversized_text() -> None:
    catalog = build_default_tool_catalog()

    for invalid_text in ("linha 1\nlinha 2", "coluna\tvalor", "x" * 513):
        try:
            catalog.build_action_request(
                ToolCall(
                    name="type_text",
                    arguments={
                        "pid": 4321,
                        "title": "Bloco de Notas",
                        "target_token": "c" * 64,
                        "text": invalid_text,
                    },
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid text input must be rejected")
