from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import ActivateWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def activate_window(self, pid: int, title: str) -> dict[str, object]:
        self.calls.append((pid, title))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "activated": True,
            "foreground_verified": True,
            "restored_from_minimized": False,
            "title_match": "bounded_title_exact",
        }


def test_activate_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = ActivateWindowAction(adapter)
    request = ActionRequest(
        action="activate_window",
        arguments={
            "pid": 4321,
            "title": "Documento - Bloco de Notas",
        },
    )

    assert action.risk is ActionRisk.NORMAL

    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [(4321, "Documento - Bloco de Notas")]
    assert result.evidence["foreground_verified"] is True
    assert "PID 4321" in result.message


def test_catalog_builds_activate_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="activate_window",
            arguments={
                "pid": 4321,
                "title": " Documento - Bloco de Notas ",
            },
        )
    )

    assert request.action == "activate_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "Documento - Bloco de Notas",
    }


def test_catalog_rejects_invalid_activate_window_target() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="activate_window",
                arguments={"pid": 0, "title": "Notepad"},
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid PID must be rejected")
