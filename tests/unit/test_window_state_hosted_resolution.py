from __future__ import annotations

import inspect

from theos.core.tools import build_default_tool_catalog
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter

_STATE_TOOLS = (
    "activate_window",
    "restore_window",
    "maximize_window",
    "minimize_window",
    "close_window",
)


def test_state_tool_schemas_remain_exact_pid_title_token_only() -> None:
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    for name in _STATE_TOOLS:
        schema = definitions[name].parameters
        assert set(schema["properties"]) == {"pid", "title", "target_token"}
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["additionalProperties"] is False


def test_state_tool_descriptions_share_hosted_alias_guidance() -> None:
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    for name in _STATE_TOOLS:
        description = definitions[name].description
        assert "ApplicationFrameHost.exe" in description
        assert "processo específico" in description
        assert "não peça esclarecimento apenas por esses aliases hospedados" in description


def test_state_actions_use_one_shared_private_resolver() -> None:
    for method_name in (
        "activate_window",
        "restore_window",
        "maximize_window",
        "minimize_window",
    ):
        source = inspect.getsource(
            getattr(WindowsDesktopWindowAdapter, method_name)
        )
        assert source.count("self._resolve_exact_window_target(") == 1
        assert "EnumWindows(" not in source


def test_close_uses_shared_resolver_with_stale_identity_detail() -> None:
    source = inspect.getsource(WindowsDesktopWindowAdapter.close_window)
    assert source.count("self._resolve_exact_window_target(") == 1
    assert "stale_detail=True" in source
    assert "EnumWindows(" not in source
    assert "WM_SYSCOMMAND" in source
    assert "SC_CLOSE" in source


def test_shared_exact_resolver_contains_hosted_dwm_normalization_only() -> None:
    source = inspect.getsource(
        WindowsDesktopWindowAdapter._resolve_exact_window_target
    )
    assert source.count("self._enumerate_action_window_candidates(") == 1
    assert "user32.EnumWindows(callback, 0)" not in source
    assert "DwmGetWindowAttribute" not in source
    assert "resolve_hosted_visual_frame_for_single_placement" in source
    assert "WINDOW_TARGET_TOKEN_STALE" in source
    assert "WINDOW_TARGET_TITLE_CHANGED" in source
    assert "SendInput" not in source
    assert "SetCursorPos" not in source
