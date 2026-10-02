from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PlaceWindowPairAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.core.window_layout_pairs import (
    ALLOWED_WINDOW_PAIR_LAYOUTS,
    WINDOW_PAIR_LAYOUT_REGISTRY,
    WINDOW_PAIR_LAYOUT_SPECS,
    HostedWindowCandidate,
    resolve_hosted_visual_frame,
    resolve_hosted_visual_frame_with_dwm_tiebreak,
)


class _FakeWindowPairAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def place_window_pair(
        self,
        first_target_token: str,
        second_target_token: str,
        arrangement: str,
    ) -> dict[str, object]:
        self.calls.append(
            (
                first_target_token,
                second_target_token,
                arrangement,
            )
        )
        spec = WINDOW_PAIR_LAYOUT_REGISTRY[arrangement]
        return {
            "arrangement": arrangement,
            "arrangement_label_pt": spec.label_pt,
            "first_pid": 100,
            "first_title": "Bloco de Notas",
            "first_process_name": "notepad.exe",
            "first_target_token": first_target_token,
            "first_placement": spec.first_placement,
            "first_rect_verified": True,
            "second_pid": 200,
            "second_title": "Calculadora",
            "second_process_name": "CalculatorApp.exe",
            "second_target_token": second_target_token,
            "second_placement": spec.second_placement,
            "second_rect_verified": True,
            "same_monitor_verified": True,
            "windows_moved": 2,
            "transactional_rollback_available": True,
            "rollback_performed": False,
            "normal_state_required": True,
            "token_only_target_resolution": True,
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_PAIR_REGISTERED_LAYOUT",
        }


def _request(arrangement: str = "SIDE_BY_SIDE") -> ActionRequest:
    return ActionRequest(
        action="place_window_pair",
        arguments={
            "first_target_token": "a" * 64,
            "second_target_token": "b" * 64,
            "arrangement": arrangement,
        },
    )


def test_window_pair_layout_registry_is_fixed_two_arrangements() -> None:
    assert tuple(WINDOW_PAIR_LAYOUT_REGISTRY) == ALLOWED_WINDOW_PAIR_LAYOUTS
    assert tuple(WINDOW_PAIR_LAYOUT_REGISTRY.values()) == WINDOW_PAIR_LAYOUT_SPECS
    assert ALLOWED_WINDOW_PAIR_LAYOUTS == ("SIDE_BY_SIDE", "STACKED")
    assert {
        spec.name: (spec.first_placement, spec.second_placement)
        for spec in WINDOW_PAIR_LAYOUT_SPECS
    } == {
        "SIDE_BY_SIDE": ("LEFT_HALF", "RIGHT_HALF"),
        "STACKED": ("TOP_HALF", "BOTTOM_HALF"),
    }
    assert all(spec.risk is ActionRisk.NORMAL for spec in WINDOW_PAIR_LAYOUT_SPECS)


def test_place_window_pair_action_uses_only_two_exact_tokens() -> None:
    adapter = _FakeWindowPairAdapter()
    action = PlaceWindowPairAction(adapter)

    assert action.risk_for(_request()) is ActionRisk.NORMAL
    result = action.execute(_request())

    assert result.success is True
    assert adapter.calls == [
        ("a" * 64, "b" * 64, "SIDE_BY_SIDE")
    ]
    assert result.evidence["first_rect_verified"] is True
    assert result.evidence["second_rect_verified"] is True
    assert result.evidence["same_monitor_verified"] is True
    assert result.evidence["token_only_target_resolution"] is True


def test_place_window_pair_action_rejects_same_exact_token() -> None:
    adapter = _FakeWindowPairAdapter()
    action = PlaceWindowPairAction(adapter)

    result = action.execute(
        ActionRequest(
            action="place_window_pair",
            arguments={
                "first_target_token": "a" * 64,
                "second_target_token": "a" * 64,
                "arrangement": "SIDE_BY_SIDE",
            },
        )
    )

    assert result.success is False
    assert result.error_code == "ACTION_VALIDATION_FAILED"
    assert adapter.calls == []


def test_catalog_builds_registered_window_pair_layout_from_tokens_only() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="place_window_pair",
            arguments={
                "first_target_token": "a" * 64,
                "second_target_token": "b" * 64,
                "arrangement": "STACKED",
            },
        )
    )

    assert request.action == "place_window_pair"
    assert request.arguments == {
        "first_target_token": "a" * 64,
        "second_target_token": "b" * 64,
        "arrangement": "STACKED",
    }


def test_catalog_rejects_unregistered_pair_layout_arbitrary_geometry_and_identity_fields() -> None:
    catalog = build_default_tool_catalog()
    base = {
        "first_target_token": "a" * 64,
        "second_target_token": "b" * 64,
        "arrangement": "SIDE_BY_SIDE",
    }

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="place_window_pair",
                arguments={**base, "arrangement": "CASCADE"},
            )
        )

    for extra in (
        "x",
        "y",
        "width",
        "height",
        "monitor",
        "percentage",
        "first_pid",
        "first_title",
        "second_pid",
        "second_title",
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="place_window_pair",
                    arguments={**base, extra: 1},
                )
            )


def test_window_pair_schema_is_token_only_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["place_window_pair"].parameters

    assert tuple(schema["properties"]["arrangement"]["enum"]) == (
        ALLOWED_WINDOW_PAIR_LAYOUTS
    )
    assert set(schema["properties"]) == {
        "first_target_token",
        "second_target_token",
        "arrangement",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    description = definitions["place_window_pair"].description
    assert "ApplicationFrameHost.exe" in description
    assert "processo específico" in description
    assert "não peça esclarecimento apenas por esses aliases hospedados" in description

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="place_window_pair",
                arguments={
                    "first_target_token": "a" * 64,
                    "second_target_token": "a" * 64,
                    "arrangement": "SIDE_BY_SIDE",
                },
            )
        )

def test_hosted_corewindow_resolves_to_unique_normal_application_frame() -> None:
    selected = HostedWindowCandidate(
        hwnd=10, pid=100, title="Calculadora", target_token="a" * 64,
        class_name="Windows.UI.Core.CoreWindow", is_iconic=False,
        is_zoomed=False, client_width=591, client_height=619,
    )
    stale_frame = HostedWindowCandidate(
        hwnd=20, pid=200, title="Calculadora", target_token="b" * 64,
        class_name="ApplicationFrameWindow", is_iconic=True,
        is_zoomed=False, client_width=0, client_height=0,
    )
    visual_frame = HostedWindowCandidate(
        hwnd=30, pid=200, title="Calculadora", target_token="c" * 64,
        class_name="ApplicationFrameWindow", is_iconic=False,
        is_zoomed=False, client_width=591, client_height=620,
    )
    resolved, normalized = resolve_hosted_visual_frame(
        selected, (selected, stale_frame, visual_frame)
    )
    assert resolved == visual_frame
    assert normalized is True


def test_hosted_visual_frame_resolution_blocks_multiple_eligible_frames() -> None:
    selected = HostedWindowCandidate(
        hwnd=10, pid=100, title="Calculadora", target_token="a" * 64,
        class_name="Windows.UI.Core.CoreWindow", is_iconic=False,
        is_zoomed=False, client_width=591, client_height=619,
    )
    frame_one = HostedWindowCandidate(
        hwnd=20, pid=200, title="Calculadora", target_token="b" * 64,
        class_name="ApplicationFrameWindow", is_iconic=False,
        is_zoomed=False, client_width=591, client_height=620,
    )
    frame_two = HostedWindowCandidate(
        hwnd=30, pid=300, title="Calculadora", target_token="c" * 64,
        class_name="ApplicationFrameWindow", is_iconic=False,
        is_zoomed=False, client_width=591, client_height=620,
    )
    with pytest.raises(ValueError, match="HOSTED_VISUAL_FRAME_AMBIGUOUS"):
        resolve_hosted_visual_frame(selected, (selected, frame_one, frame_two))

def _shared_hosted_candidate(
    hwnd: int,
    *,
    class_name: str,
    token_char: str,
) -> HostedWindowCandidate:
    return HostedWindowCandidate(
        hwnd=hwnd,
        pid=1000 + hwnd,
        title="Calculadora",
        target_token=token_char * 64,
        class_name=class_name,
        is_iconic=False,
        is_zoomed=False,
        client_width=600,
        client_height=620,
    )


def test_shared_hosted_resolver_uses_unique_uncloaked_frame_on_ambiguity() -> None:
    selected = _shared_hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    active = _shared_hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    stale = _shared_hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    resolved, normalized, tie_break_used = (
        resolve_hosted_visual_frame_with_dwm_tiebreak(
            selected,
            (selected, active, stale),
            {20: 0, 30: 2},
        )
    )

    assert resolved == active
    assert normalized is True
    assert tie_break_used is True


def test_shared_hosted_resolver_blocks_zero_uncloaked_frames_on_ambiguity() -> None:
    selected = _shared_hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    first = _shared_hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    second = _shared_hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    with pytest.raises(ValueError, match="HOSTED_VISUAL_FRAME_AMBIGUOUS"):
        resolve_hosted_visual_frame_with_dwm_tiebreak(
            selected,
            (selected, first, second),
            {20: 2, 30: 2},
        )


def test_shared_hosted_resolver_blocks_multiple_uncloaked_frames_on_ambiguity() -> None:
    selected = _shared_hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    first = _shared_hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    second = _shared_hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    with pytest.raises(ValueError, match="HOSTED_VISUAL_FRAME_AMBIGUOUS"):
        resolve_hosted_visual_frame_with_dwm_tiebreak(
            selected,
            (selected, first, second),
            {20: 0, 30: 0},
        )


def test_shared_hosted_resolver_does_not_gate_single_frame_on_dwm_value() -> None:
    selected = _shared_hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    only_frame = _shared_hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )

    resolved, normalized, tie_break_used = (
        resolve_hosted_visual_frame_with_dwm_tiebreak(
            selected,
            (selected, only_frame),
            {20: 2},
        )
    )

    assert resolved == only_frame
    assert normalized is True
    assert tie_break_used is False
