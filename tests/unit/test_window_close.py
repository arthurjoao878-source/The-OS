from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import CloseWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


class _FakeCloseAdapter:
    def __init__(self) -> None:
        self.close_calls: list[tuple[int, str, str]] = []

    def close_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        self.close_calls.append((pid, title, target_token))
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "close_requested": True,
            "window_gone_verified": True,
            "verification": "original_exact_window_destroyed_or_not_visible",
            "close_method": "WM_SYSCOMMAND_SC_CLOSE",
            "force_kill_used": False,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_close_window_requires_preview_guard() -> None:
    adapter = _FakeCloseAdapter()
    action = CloseWindowAction(adapter)
    request = ActionRequest(
        action="close_window",
        arguments={
            "pid": 4321,
            "title": "M31-LIVE - Bloco de Notas",
            "target_token": "a" * 64,
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
    assert "Alvo opaco: aaaaaaaaaaaa..." in preview.text
    assert adapter.close_calls == []

    request.arguments.update(preview.execution_guard)
    result = action.execute(request)

    assert result.success is True
    assert adapter.close_calls == [
        (4321, "M31-LIVE - Bloco de Notas", "a" * 64)
    ]
    assert result.evidence["target_token"] == "a" * 64
    assert result.evidence["window_gone_verified"] is True
    assert result.evidence["verification"] == (
        "original_exact_window_destroyed_or_not_visible"
    )
    assert result.evidence["force_kill_used"] is False


def test_catalog_builds_close_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="close_window",
            arguments={
                "pid": 4321,
                "title": " M31-LIVE - Bloco de Notas ",
                "target_token": "b" * 64,
            },
        )
    )

    assert request.action == "close_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "M31-LIVE - Bloco de Notas",
        "target_token": "b" * 64,
    }


def test_catalog_rejects_invalid_close_window_target_token() -> None:
    catalog = build_default_tool_catalog()

    try:
        catalog.build_action_request(
            ToolCall(
                name="close_window",
                arguments={
                    "pid": 4321,
                    "title": "M31-LIVE - Bloco de Notas",
                    "target_token": "BAD",
                },
            )
        )
    except ToolValidationError:
        pass
    else:
        raise AssertionError("invalid close-window target token must be rejected")

def test_close_window_reports_stale_exact_target_without_fallback() -> None:
    class _StaleTargetAdapter:
        def close_window(
            self,
            pid: int,
            title: str,
            target_token: str,
        ) -> dict[str, object]:
            _ = pid, title, target_token
            raise RuntimeError("WINDOW_TARGET_TOKEN_STALE")

    action = CloseWindowAction(_StaleTargetAdapter())
    request = ActionRequest(
        action="close_window",
        arguments={
            "pid": 4321,
            "title": "M31-LIVE - Bloco de Notas",
            "target_token": "d" * 64,
        },
    )
    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    request.arguments.update(preview.execution_guard)

    result = action.execute(request)

    assert result.success is False
    assert result.error_code == "WINDOW_TARGET_TOKEN_STALE"
    assert result.evidence["diagnosis"] == (
        "same_pid_title_but_target_token_changed"
    )
