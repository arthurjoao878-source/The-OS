from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping

from theos.core.window_targets import is_window_target_token

WINDOW_OBSERVATION_HANDLE_VERSION = 1
WINDOW_OBSERVATION_TTL_SECONDS = 120
WINDOW_OBSERVATION_RESOURCE = "window"
WINDOW_OBSERVATION_ID_CHARS = 32
WINDOW_OBSERVATION_SIGNATURE_CHARS = 64
WINDOW_OBSERVATION_MAX_FUTURE_SKEW_SECONDS = 5

_WINDOW_OBSERVATION_KEY = secrets.token_bytes(32)
_REQUIRED_HANDLE_KEYS = frozenset(
    {
        "version",
        "observation_id",
        "resource",
        "element_ref",
        "observed_at",
        "expires_at",
        "signature",
    }
)


class WindowObservationHandleError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _signature_payload(
    *,
    version: int,
    observation_id: str,
    resource: str,
    element_ref: str,
    observed_at: int,
    expires_at: int,
) -> bytes:
    return (
        f"{version}\0{observation_id}\0{resource}\0{element_ref}\0"
        f"{observed_at}\0{expires_at}"
    ).encode()


def _signature_for(
    *,
    version: int,
    observation_id: str,
    resource: str,
    element_ref: str,
    observed_at: int,
    expires_at: int,
) -> str:
    payload = _signature_payload(
        version=version,
        observation_id=observation_id,
        resource=resource,
        element_ref=element_ref,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    return hmac.new(
        _WINDOW_OBSERVATION_KEY,
        payload,
        hashlib.sha256,
    ).hexdigest()


def build_window_observation_handle(
    target_token: str,
    *,
    now: float | None = None,
    observation_id: str | None = None,
) -> dict[str, object]:
    if not is_window_target_token(target_token):
        raise ValueError("target_token must be a valid window target token")

    observed_at = int(time.time() if now is None else now)
    if observed_at < 0:
        raise ValueError("now must not be negative")

    handle_id = (
        secrets.token_hex(WINDOW_OBSERVATION_ID_CHARS // 2)
        if observation_id is None
        else observation_id
    )
    if not _is_lower_hex(handle_id, WINDOW_OBSERVATION_ID_CHARS):
        raise ValueError("observation_id must be lowercase hex")

    expires_at = observed_at + WINDOW_OBSERVATION_TTL_SECONDS
    signature = _signature_for(
        version=WINDOW_OBSERVATION_HANDLE_VERSION,
        observation_id=handle_id,
        resource=WINDOW_OBSERVATION_RESOURCE,
        element_ref=target_token,
        observed_at=observed_at,
        expires_at=expires_at,
    )

    return {
        "version": WINDOW_OBSERVATION_HANDLE_VERSION,
        "observation_id": handle_id,
        "resource": WINDOW_OBSERVATION_RESOURCE,
        "element_ref": target_token,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "signature": signature,
    }


def validate_window_observation_handle(
    value: object,
    *,
    expected_target_token: str,
    now: float | None = None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _REQUIRED_HANDLE_KEYS:
        raise WindowObservationHandleError("WINDOW_OBSERVATION_HANDLE_INVALID")

    version = value.get("version")
    observation_id = value.get("observation_id")
    resource = value.get("resource")
    element_ref = value.get("element_ref")
    observed_at = value.get("observed_at")
    expires_at = value.get("expires_at")
    signature = value.get("signature")

    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != WINDOW_OBSERVATION_HANDLE_VERSION
        or not _is_lower_hex(observation_id, WINDOW_OBSERVATION_ID_CHARS)
        or resource != WINDOW_OBSERVATION_RESOURCE
        or not is_window_target_token(element_ref)
        or not isinstance(observed_at, int)
        or isinstance(observed_at, bool)
        or observed_at < 0
        or not isinstance(expires_at, int)
        or isinstance(expires_at, bool)
        or expires_at != observed_at + WINDOW_OBSERVATION_TTL_SECONDS
        or not _is_lower_hex(signature, WINDOW_OBSERVATION_SIGNATURE_CHARS)
    ):
        raise WindowObservationHandleError("WINDOW_OBSERVATION_HANDLE_INVALID")

    expected_signature = _signature_for(
        version=version,
        observation_id=observation_id,
        resource=resource,
        element_ref=element_ref,
        observed_at=observed_at,
        expires_at=expires_at,
    )
    if not hmac.compare_digest(signature, expected_signature):
        raise WindowObservationHandleError("WINDOW_OBSERVATION_HANDLE_INVALID")

    if element_ref != expected_target_token:
        raise WindowObservationHandleError("WINDOW_OBSERVATION_TARGET_MISMATCH")

    current = int(time.time() if now is None else now)
    if observed_at > current + WINDOW_OBSERVATION_MAX_FUTURE_SKEW_SECONDS:
        raise WindowObservationHandleError("WINDOW_OBSERVATION_HANDLE_INVALID")
    if current > expires_at:
        raise WindowObservationHandleError("WINDOW_OBSERVATION_EXPIRED")

    return {
        "version": version,
        "observation_id": observation_id,
        "resource": resource,
        "element_ref": element_ref,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "signature": signature,
    }
