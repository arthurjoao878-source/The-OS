from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ActivateWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def activate_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "activated": True,
            "foreground_verified": True,
            "restored_from_minimized": False,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_activate_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = ActivateWindowAction(adapter)
    request = ActionRequest(
        action="activate_window",
        arguments={
            "pid": 4321,
            "title": "Documento - Bloco de Notas",
            "target_token": "a" * 64,
        },
    )

    assert action.risk is ActionRisk.NORMAL

    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Documento - Bloco de Notas", "a" * 64)
    ]
    assert result.evidence["foreground_verified"] is True
    assert result.evidence["target_token"] == "a" * 64
    assert result.evidence["title_match"] == (
        "pid_bounded_title_and_opaque_token_exact"
    )
    assert "PID 4321" in result.message


def test_catalog_builds_activate_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="activate_window",
            arguments={
                "pid": 4321,
                "title": " Documento - Bloco de Notas ",
                "target_token": "b" * 64,
            },
        )
    )

    assert request.action == "activate_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "Documento - Bloco de Notas",
        "target_token": "b" * 64,
    }


def test_catalog_rejects_invalid_activate_window_target() -> None:
    catalog = build_default_tool_catalog()

    invalid_arguments = (
        {
            "pid": 0,
            "title": "Notepad",
            "target_token": "c" * 64,
        },
        {
            "pid": 4321,
            "title": "Notepad",
            "target_token": "not-a-token",
        },
    )
    for arguments in invalid_arguments:
        try:
            catalog.build_action_request(
                ToolCall(
                    name="activate_window",
                    arguments=arguments,
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid exact window target must be rejected")


def test_activate_window_action_rejects_invalid_target_token() -> None:
    adapter = _FakeWindowAdapter()
    action = ActivateWindowAction(adapter)
    request = ActionRequest(
        action="activate_window",
        arguments={
            "pid": 4321,
            "title": "Documento - Bloco de Notas",
            "target_token": "bad",
        },
    )

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "ACTION_VALIDATION_FAILED"
    assert adapter.calls == []
