from __future__ import annotations

import pytest

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import PlaceWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.core.window_placements import (
    ALLOWED_WINDOW_PLACEMENTS,
    WINDOW_PLACEMENT_REGISTRY,
    WINDOW_PLACEMENT_SPECS,
)


class _FakeWindowPlacementAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str, str]] = []

    def place_window(
        self,
        pid: int,
        title: str,
        target_token: str,
        placement: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token, placement))
        spec = WINDOW_PLACEMENT_REGISTRY[placement]
        return {
            "pid": pid,
            "title": title,
            "process_name": "notepad.exe",
            "target_token": target_token,
            "placement": placement,
            "placement_label_pt": spec.label_pt,
            "position_mode": "monitor_work_area_registered_layout",
            "monitor_work_area_left": 0,
            "monitor_work_area_top": 0,
            "monitor_work_area_right": 1920,
            "monitor_work_area_bottom": 1040,
            "monitor_work_area_width": 1920,
            "monitor_work_area_height": 1040,
            "target_left": 0,
            "target_top": 0,
            "target_right": 960,
            "target_bottom": 1040,
            "target_width": 960,
            "target_height": 1040,
            "window_rect_verified": True,
            "was_minimized": False,
            "was_maximized": False,
            "restored_to_normal_before_move": False,
            "native_snap_semantics_claimed": False,
            "content_effect_verified": False,
            "input_method": "MoveWindow_MONITOR_WORK_AREA_REGISTERED_LAYOUT",
            "placement_allowlist": list(ALLOWED_WINDOW_PLACEMENTS),
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_window_placement_registry_is_fixed_eleven_layout_policy_source() -> None:
    assert tuple(WINDOW_PLACEMENT_REGISTRY) == ALLOWED_WINDOW_PLACEMENTS
    assert tuple(WINDOW_PLACEMENT_REGISTRY.values()) == WINDOW_PLACEMENT_SPECS
    assert ALLOWED_WINDOW_PLACEMENTS == (
        "LEFT_HALF",
        "RIGHT_HALF",
        "TOP_HALF",
        "BOTTOM_HALF",
        "LEFT_THIRD",
        "CENTER_THIRD",
        "RIGHT_THIRD",
        "UPPER_LEFT_QUADRANT",
        "UPPER_RIGHT_QUADRANT",
        "LOWER_LEFT_QUADRANT",
        "LOWER_RIGHT_QUADRANT",
    )
    assert {
        spec.name: (
            spec.x_percent,
            spec.y_percent,
            spec.width_percent,
            spec.height_percent,
        )
        for spec in WINDOW_PLACEMENT_SPECS
    } == {
        "LEFT_HALF": (0, 0, 50, 100),
        "RIGHT_HALF": (50, 0, 50, 100),
        "TOP_HALF": (0, 0, 100, 50),
        "BOTTOM_HALF": (0, 50, 100, 50),
        "LEFT_THIRD": (0, 0, 33, 100),
        "CENTER_THIRD": (33, 0, 34, 100),
        "RIGHT_THIRD": (67, 0, 33, 100),
        "UPPER_LEFT_QUADRANT": (0, 0, 50, 50),
        "UPPER_RIGHT_QUADRANT": (50, 0, 50, 50),
        "LOWER_LEFT_QUADRANT": (0, 50, 50, 50),
        "LOWER_RIGHT_QUADRANT": (50, 50, 50, 50),
    }
    assert all(spec.risk is ActionRisk.NORMAL for spec in WINDOW_PLACEMENT_SPECS)


def test_place_window_action_uses_exact_known_target_and_registered_layout() -> None:
    adapter = _FakeWindowPlacementAdapter()
    action = PlaceWindowAction(adapter)
    request = ActionRequest(
        action="place_window",
        arguments={
            "pid": 4321,
            "title": "Sem título - Bloco de Notas",
            "target_token": "a" * 64,
            "placement": "LEFT_HALF",
        },
    )

    assert action.risk_for(request) is ActionRisk.NORMAL
    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == [
        (4321, "Sem título - Bloco de Notas", "a" * 64, "LEFT_HALF")
    ]
    assert result.evidence["window_rect_verified"] is True
    assert result.evidence["native_snap_semantics_claimed"] is False
    assert result.evidence["position_mode"] == (
        "monitor_work_area_registered_layout"
    )


def test_catalog_builds_registered_window_placement() -> None:
    catalog = build_default_tool_catalog()
    request = catalog.build_action_request(
        ToolCall(
            name="place_window",
            arguments={
                "pid": 5001,
                "title": " Bloco de Notas ",
                "target_token": "b" * 64,
                "placement": "LOWER_RIGHT_QUADRANT",
            },
        )
    )

    assert request.action == "place_window"
    assert request.arguments == {
        "pid": 5001,
        "title": "Bloco de Notas",
        "target_token": "b" * 64,
        "placement": "LOWER_RIGHT_QUADRANT",
    }


def test_catalog_rejects_unregistered_window_placement() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="place_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "c" * 64,
                    "placement": "FULL_SCREEN",
                },
            )
        )


def test_catalog_rejects_arbitrary_window_geometry() -> None:
    catalog = build_default_tool_catalog()

    for extra in (
        {"x": 10},
        {"y": 20},
        {"width": 800},
        {"height": 600},
        {"monitor": 2},
    ):
        with pytest.raises(ToolValidationError):
            catalog.build_action_request(
                ToolCall(
                    name="place_window",
                    arguments={
                        "pid": 5001,
                        "title": "Bloco de Notas",
                        "target_token": "d" * 64,
                        "placement": "RIGHT_HALF",
                        **extra,
                    },
                )
            )


def test_window_placement_schema_is_registry_driven_and_strict() -> None:
    catalog = build_default_tool_catalog()
    definitions = {definition.name: definition for definition in catalog.definitions()}
    schema = definitions["place_window"].parameters

    assert tuple(schema["properties"]["placement"]["enum"]) == (
        ALLOWED_WINDOW_PLACEMENTS
    )
    assert set(schema["properties"]) == {
        "pid",
        "title",
        "target_token",
        "placement",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False

def test_window_placement_v2_partitions_cover_full_work_area_without_overlap() -> None:
    top = WINDOW_PLACEMENT_REGISTRY["TOP_HALF"]
    bottom = WINDOW_PLACEMENT_REGISTRY["BOTTOM_HALF"]
    left = WINDOW_PLACEMENT_REGISTRY["LEFT_THIRD"]
    center = WINDOW_PLACEMENT_REGISTRY["CENTER_THIRD"]
    right = WINDOW_PLACEMENT_REGISTRY["RIGHT_THIRD"]

    assert (top.y_percent, top.height_percent) == (0, 50)
    assert (bottom.y_percent, bottom.height_percent) == (50, 50)
    assert top.height_percent + bottom.height_percent == 100

    assert (left.x_percent, left.width_percent) == (0, 33)
    assert (center.x_percent, center.width_percent) == (33, 34)
    assert (right.x_percent, right.width_percent) == (67, 33)
    assert left.x_percent + left.width_percent == center.x_percent
    assert center.x_percent + center.width_percent == right.x_percent
    assert right.x_percent + right.width_percent == 100


def test_catalog_builds_all_window_layout_v2_batch_names() -> None:
    catalog = build_default_tool_catalog()
    for placement in (
        "TOP_HALF",
        "BOTTOM_HALF",
        "LEFT_THIRD",
        "CENTER_THIRD",
        "RIGHT_THIRD",
    ):
        request = catalog.build_action_request(
            ToolCall(
                name="place_window",
                arguments={
                    "pid": 5001,
                    "title": "Bloco de Notas",
                    "target_token": "e" * 64,
                    "placement": placement,
                },
            )
        )
        assert request.arguments["placement"] == placement
