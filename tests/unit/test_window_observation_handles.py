from __future__ import annotations

import time

import pytest

from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.core.window_observations import (
    WINDOW_OBSERVATION_HANDLE_VERSION,
    WINDOW_OBSERVATION_TTL_SECONDS,
    WindowObservationHandleError,
    build_window_observation_handle,
    validate_window_observation_handle,
)

_TOKEN_A = "a" * 64
_TOKEN_B = "b" * 64


def test_window_observation_handle_round_trip_is_structured_and_bounded() -> None:
    handle = build_window_observation_handle(
        _TOKEN_A,
        now=1_000,
        observation_id="1" * 32,
    )

    assert handle == {
        "version": WINDOW_OBSERVATION_HANDLE_VERSION,
        "observation_id": "1" * 32,
        "resource": "window",
        "element_ref": _TOKEN_A,
        "observed_at": 1_000,
        "expires_at": 1_000 + WINDOW_OBSERVATION_TTL_SECONDS,
        "signature": handle["signature"],
    }
    assert len(str(handle["signature"])) == 64
    assert validate_window_observation_handle(
        handle,
        expected_target_token=_TOKEN_A,
        now=1_001,
    ) == handle


def test_window_observation_handle_expires() -> None:
    handle = build_window_observation_handle(
        _TOKEN_A,
        now=1_000,
        observation_id="2" * 32,
    )

    with pytest.raises(WindowObservationHandleError) as exc_info:
        validate_window_observation_handle(
            handle,
            expected_target_token=_TOKEN_A,
            now=1_000 + WINDOW_OBSERVATION_TTL_SECONDS + 1,
        )

    assert exc_info.value.code == "WINDOW_OBSERVATION_EXPIRED"


def test_window_observation_handle_is_bound_to_target_token() -> None:
    handle = build_window_observation_handle(
        _TOKEN_A,
        now=1_000,
        observation_id="3" * 32,
    )

    with pytest.raises(WindowObservationHandleError) as exc_info:
        validate_window_observation_handle(
            handle,
            expected_target_token=_TOKEN_B,
            now=1_001,
        )

    assert exc_info.value.code == "WINDOW_OBSERVATION_TARGET_MISMATCH"


def test_window_observation_handle_rejects_tampering() -> None:
    handle = build_window_observation_handle(
        _TOKEN_A,
        now=1_000,
        observation_id="4" * 32,
    )
    tampered = dict(handle)
    tampered["signature"] = "0" * 64

    with pytest.raises(WindowObservationHandleError) as exc_info:
        validate_window_observation_handle(
            tampered,
            expected_target_token=_TOKEN_A,
            now=1_001,
        )

    assert exc_info.value.code == "WINDOW_OBSERVATION_HANDLE_INVALID"


def test_maximize_tool_catalog_uses_required_nullable_observation_handle() -> None:
    handle = build_window_observation_handle(
        _TOKEN_A,
        now=int(time.time()),
    )
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="maximize_window",
            arguments={
                "pid": 4321,
                "title": "Calculadora",
                "target_token": _TOKEN_A,
                "observation_handle": handle,
            },
        )
    )

    assert request.action == "maximize_window"
    assert request.arguments["observation_handle"] == handle
    definition = next(
        item
        for item in catalog.definitions()
        if item.name == "maximize_window"
    )
    assert "observation_handle" in definition.parameters["properties"]
    assert definition.parameters["required"] == [
        "pid",
        "title",
        "target_token",
        "observation_handle",
    ]
    handle_schema = definition.parameters["properties"]["observation_handle"]
    assert handle_schema["type"] == ["object", "null"]
    assert set(handle_schema["required"]) == set(handle_schema["properties"])
    assert handle_schema["additionalProperties"] is False
