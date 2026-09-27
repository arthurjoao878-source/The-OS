from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import CloseWindowAction
from theos.core.tools import ToolCall, build_default_tool_catalog


class _FakeCloseAdapter:
    def __init__(self) -> None:
        self.close_calls: list[tuple[int, str]] = []

    def close_window(self, pid: int, title: str) -> dict[str, object]:
        self.close_calls.append((pid, title))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "close_requested": True,
            "window_gone_verified": True,
            "verification": "original_window_destroyed_or_not_visible",
            "close_method": "WM_SYSCOMMAND_SC_CLOSE",
            "force_kill_used": False,
        }


def test_close_window_requires_preview_guard() -> None:
    adapter = _FakeCloseAdapter()
    action = CloseWindowAction(adapter)
    request = ActionRequest(
        action="close_window",
        arguments={
            "pid": 4321,
            "title": "M19-LIVE.txt - Bloco de Notas",
        },
    )

    assert action.risk is ActionRisk.DESTRUCTIVE

    blocked = action.execute(request)
    assert blocked.success is False
    assert blocked.error_code == "WINDOW_CLOSE_PREVIEW_REQUIRED"
    assert adapter.close_calls == []

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "FECHAR JANELA" in preview.text
    assert "trabalho não salvo" in preview.text
    assert "WM_SYSCOMMAND/SC_CLOSE" in preview.text
    assert adapter.close_calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.close_calls == [(4321, "M19-LIVE.txt - Bloco de Notas")]
    assert result.evidence["window_gone_verified"] is True
    assert result.evidence["verification"] == "original_window_destroyed_or_not_visible"
    assert result.evidence["force_kill_used"] is False


def test_catalog_builds_close_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="close_window",
            arguments={
                "pid": 4321,
                "title": " M19-LIVE.txt - Bloco de Notas ",
            },
        )
    )

    assert request.action == "close_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "M19-LIVE.txt - Bloco de Notas",
    }
