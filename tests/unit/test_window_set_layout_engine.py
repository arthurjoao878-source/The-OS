from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PlaceWindowSetAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.core.window_layout_pairs import HostedWindowCandidate
from theos.core.window_layout_sets import (
    ALLOWED_WINDOW_SET_LAYOUTS,
    WINDOW_SET_LAYOUT_REGISTRY,
    WINDOW_SET_LAYOUT_SPECS,
    resolve_hosted_visual_frame_for_set,
)


class _FakeWindowSetAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def place_window_set(
        self,
        target_tokens: tuple[str, ...],
        arrangement: str,
    ) -> dict[str, object]:
        self.calls.append((target_tokens, arrangement))
        spec = WINDOW_SET_LAYOUT_REGISTRY[arrangement]
        targets = [
            {
                "index": index,
                "pid": 100 + index,
                "title": f"Janela {index}",
                "process_name": f"app{index}.exe",
                "requested_target_token": token,
                "placement": placement,
                "rect_verified": True,
                "resolved_window_class": "TestWindow",
                "visual_frame_normalized": False,
            }
            for index, (token, placement) in enumerate(
                zip(target_tokens, spec.placements, strict=True),
                start=1,
            )
        ]
        return {
            "arrangement": arrangement,
            "arrangement_label_pt": spec.label_pt,
            "window_count": len(targets),
            "targets": targets,
            "same_monitor_verified": True,
            "windows_moved": len(targets),
            "transactional_rollback_available": True,
            "rollback_performed": False,
            "normal_state_required": True,
            "token_only_target_resolution": True,
            "hosted_visual_frame_resolution": True,
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_SET_REGISTERED_LAYOUT",
        }


def _tokens(count: int) -> tuple[str, ...]:
    return tuple(f"{index:064x}" for index in range(1, count + 1))


def _request(
    arrangement: str = "THREE_COLUMNS",
    count: int = 3,
) -> ActionRequest:
    return ActionRequest(
        action="place_window_set",
        arguments={
            "target_tokens": list(_tokens(count)),
            "arrangement": arrangement,
        },
    )


def test_window_set_registry_is_fixed_and_complete() -> None:
    assert tuple(WINDOW_SET_LAYOUT_REGISTRY) == ALLOWED_WINDOW_SET_LAYOUTS
    assert tuple(WINDOW_SET_LAYOUT_REGISTRY.values()) == WINDOW_SET_LAYOUT_SPECS
    assert ALLOWED_WINDOW_SET_LAYOUTS == (
        "THREE_COLUMNS",
        "LEFT_MAIN_RIGHT_STACK",
        "RIGHT_MAIN_LEFT_STACK",
        "FOUR_QUADRANTS",
    )
    assert {
        spec.name: spec.placements
        for spec in WINDOW_SET_LAYOUT_SPECS
    } == {
        "THREE_COLUMNS": (
            "LEFT_THIRD",
            "CENTER_THIRD",
            "RIGHT_THIRD",
        ),
        "LEFT_MAIN_RIGHT_STACK": (
            "LEFT_HALF",
            "UPPER_RIGHT_QUADRANT",
            "LOWER_RIGHT_QUADRANT",
        ),
        "RIGHT_MAIN_LEFT_STACK": (
            "RIGHT_HALF",
            "UPPER_LEFT_QUADRANT",
            "LOWER_LEFT_QUADRANT",
        ),
        "FOUR_QUADRANTS": (
            "UPPER_LEFT_QUADRANT",
            "UPPER_RIGHT_QUADRANT",
            "LOWER_LEFT_QUADRANT",
            "LOWER_RIGHT_QUADRANT",
        ),
    }
    assert [spec.target_count for spec in WINDOW_SET_LAYOUT_SPECS] == [3, 3, 3, 4]
    assert all(spec.risk is ActionRisk.NORMAL for spec in WINDOW_SET_LAYOUT_SPECS)


def test_place_window_set_action_uses_three_exact_tokens() -> None:
    adapter = _FakeWindowSetAdapter()
    action = PlaceWindowSetAction(adapter)

    assert action.risk_for(_request()) is ActionRisk.NORMAL
    result = action.execute(_request())

    assert result.success is True
    assert adapter.calls == [(_tokens(3), "THREE_COLUMNS")]
    assert result.evidence["window_count"] == 3
    assert result.evidence["same_monitor_verified"] is True
    assert result.evidence["transactional_rollback_available"] is True


def test_place_window_set_action_rejects_duplicate_token() -> None:
    adapter = _FakeWindowSetAdapter()
    action = PlaceWindowSetAction(adapter)
    tokens = list(_tokens(3))
    tokens[2] = tokens[1]

    result = action.execute(
        ActionRequest(
            action="place_window_set",
            arguments={
                "target_tokens": tokens,
                "arrangement": "THREE_COLUMNS",
            },
        )
    )

    assert result.success is False
    assert result.error_code == "ACTION_VALIDATION_FAILED"
    assert adapter.calls == []


def test_place_window_set_action_rejects_layout_count_mismatch() -> None:
    adapter = _FakeWindowSetAdapter()
    action = PlaceWindowSetAction(adapter)

    result = action.execute(_request("FOUR_QUADRANTS", count=3))

    assert result.success is False
    assert result.error_code == "ACTION_VALIDATION_FAILED"
    assert adapter.calls == []


def test_catalog_builds_registered_three_window_set() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="place_window_set",
            arguments={
                "target_tokens": list(_tokens(3)),
                "arrangement": "LEFT_MAIN_RIGHT_STACK",
            },
        )
    )

    assert request.action == "place_window_set"
    assert request.arguments == {
        "target_tokens": list(_tokens(3)),
        "arrangement": "LEFT_MAIN_RIGHT_STACK",
    }


def test_catalog_builds_registered_four_window_set() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="place_window_set",
            arguments={
                "target_tokens": list(_tokens(4)),
                "arrangement": "FOUR_QUADRANTS",
            },
        )
    )

    assert request.arguments["target_tokens"] == list(_tokens(4))
    assert request.arguments["arrangement"] == "FOUR_QUADRANTS"


def test_catalog_rejects_invalid_set_shapes_and_arbitrary_geometry() -> None:
    catalog = build_default_tool_catalog()

    invalid_calls = (
        {
            "target_tokens": list(_tokens(2)),
            "arrangement": "THREE_COLUMNS",
        },
        {
            "target_tokens": list(_tokens(4)),
            "arrangement": "THREE_COLUMNS",
        },
        {
            "target_tokens": list(_tokens(3)),
            "arrangement": "CASCADE",
        },
        {
            "target_tokens": [
                _tokens(3)[0],
                _tokens(3)[1],
                _tokens(3)[1],
            ],
            "arrangement": "THREE_COLUMNS",
        },
        {
            "target_tokens": list(_tokens(3)),
            "arrangement": "THREE_COLUMNS",
            "x": 1,
        },
    )
    for arguments in invalid_calls:
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="place_window_set",
                    arguments=arguments,
                )
            )


def test_window_set_schema_is_token_only_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {
        definition.name: definition
        for definition in catalog.definitions()
    }
    schema = definitions["place_window_set"].parameters

    assert set(schema["properties"]) == {
        "target_tokens",
        "arrangement",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    token_schema = schema["properties"]["target_tokens"]
    assert token_schema["type"] == "array"
    assert token_schema["minItems"] == 3
    assert token_schema["maxItems"] == 4
    assert "uniqueItems" not in token_schema
    assert tuple(schema["properties"]["arrangement"]["enum"]) == (
        ALLOWED_WINDOW_SET_LAYOUTS
    )
    description = definitions["place_window_set"].description
    assert "ApplicationFrameHost.exe" in description
    assert "processo específico" in description
    assert "não peça esclarecimento apenas por esses aliases hospedados" in description

def _hosted_candidate(
    hwnd: int,
    *,
    class_name: str,
    token_char: str,
) -> HostedWindowCandidate:
    return HostedWindowCandidate(
        hwnd=hwnd,
        pid=100 + hwnd,
        title="Calculadora",
        target_token=token_char * 64,
        class_name=class_name,
        is_iconic=False,
        is_zoomed=False,
        client_width=600,
        client_height=620,
    )


def test_window_set_hosted_ambiguity_uses_unique_uncloaked_frame() -> None:
    selected = _hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    active = _hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    stale = _hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    resolved, normalized, tie_break_used = resolve_hosted_visual_frame_for_set(
        selected,
        (selected, active, stale),
        {20: 0, 30: 2},
    )

    assert resolved == active
    assert normalized is True
    assert tie_break_used is True


def test_window_set_hosted_ambiguity_blocks_without_unique_uncloaked_frame() -> None:
    selected = _hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    first = _hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    second = _hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    with pytest.raises(ValueError, match="HOSTED_VISUAL_FRAME_AMBIGUOUS"):
        resolve_hosted_visual_frame_for_set(
            selected,
            (selected, first, second),
            {20: 2, 30: 2},
        )


def test_window_set_hosted_ambiguity_blocks_multiple_uncloaked_frames() -> None:
    selected = _hosted_candidate(
        10,
        class_name="Windows.UI.Core.CoreWindow",
        token_char="a",
    )
    first = _hosted_candidate(
        20,
        class_name="ApplicationFrameWindow",
        token_char="b",
    )
    second = _hosted_candidate(
        30,
        class_name="ApplicationFrameWindow",
        token_char="c",
    )

    with pytest.raises(ValueError, match="HOSTED_VISUAL_FRAME_AMBIGUOUS"):
        resolve_hosted_visual_frame_for_set(
            selected,
            (selected, first, second),
            {20: 0, 30: 0},
        )
