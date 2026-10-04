from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ActionRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    NORMAL = "NORMAL"
    CONFIRM = "CONFIRM"
    DESTRUCTIVE = "DESTRUCTIVE"
    PRIVILEGED = "PRIVILEGED"


class ActionRequest(BaseModel):
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: UUID = Field(default_factory=uuid4)


class ActionResult(BaseModel):
    request_id: UUID
    success: bool
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    effect_dispatched: bool | None = None
    postcondition_verified: bool | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationPreview:
    allowed: bool
    text: str
    execution_guard: dict[str, Any] = field(default_factory=dict)
