from __future__ import annotations

from theos.core.tools import build_default_tool_catalog
from theos.core.window_layout_pairs import (
    HostedWindowCandidate,
    resolve_hosted_visual_frame_for_single_placement,
)


def _candidate(
    hwnd: int,
    *,
    class_name: str,
    token_char: str,
    is_iconic: bool = False,
    is_zoomed: bool = False,
) -> HostedWindowCandidate:
    return HostedWindowCandidate(
        hwnd=hwnd,
        pid=1000 + hwnd,
        title="Calculadora",
        target_token=token_char * 64,
        class_name=class_name,
        is_iconic=is_iconic,
        is_zoomed=is_zoomed,
        client_width=600,
        client_height=620,
    )


def test_single_placement_corewindow_uses_unique_uncloaked_visual_frame() -> None:
    selected = _candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    active = _candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    stale = _candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    resolved, normalized, tie_break_used = (
        resolve_hosted_visual_frame_for_single_placement(
            selected,
            (selected, active, stale),
            {20: 0, 30: 2},
        )
    )

    assert resolved == active
    assert normalized is True
    assert tie_break_used is True


def test_single_placement_can_resolve_one_non_normal_visual_frame_for_restore() -> None:
    selected = _candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    minimized_frame = _candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
        is_iconic=True,
    )

    resolved, normalized, tie_break_used = (
        resolve_hosted_visual_frame_for_single_placement(
            selected,
            (selected, minimized_frame),
            {20: 2},
        )
    )

    assert resolved == minimized_frame
    assert normalized is True
    assert tie_break_used is False


def test_single_placement_direct_frame_preserves_existing_restore_semantics() -> None:
    selected_frame = _candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
        is_zoomed=True,
    )
    other_frame = _candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    resolved, normalized, tie_break_used = (
        resolve_hosted_visual_frame_for_single_placement(
            selected_frame,
            (selected_frame, other_frame),
            {20: 2, 30: 0},
        )
    )

    assert resolved == selected_frame
    assert normalized is False
    assert tie_break_used is False


def test_single_placement_provider_guidance_uses_application_specific_alias() -> None:
    definitions = {
        definition.name: definition
        for definition in build_default_tool_catalog().definitions()
    }
    description = definitions["place_window"].description
    assert "ApplicationFrameHost.exe" in description
    assert "processo específico" in description
    assert "não peça esclarecimento apenas por esses aliases hospedados" in description

    schema = definitions["place_window"].parameters
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "placement",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
