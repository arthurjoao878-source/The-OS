from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4


class MemoryCategory(StrEnum):
    SESSION = "session"
    SHORT_TERM = "short_term"
    PERSONAL = "personal"
    PROJECT = "project"
    SYSTEM = "system"
    HISTORY = "history"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    TOMBSTONED = "tombstoned"


def memory_content_digest(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("memory content must not be blank")
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: UUID = field(default_factory=uuid4)
    category: MemoryCategory = MemoryCategory.PERSONAL
    scope: str = "user"
    content: str | None = None
    content_digest: str = ""
    version: int = 1
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    provenance: str = "user_explicit"

    def __post_init__(self) -> None:
        if not isinstance(self.memory_id, UUID):
            raise TypeError("memory_id must be UUID")
        if not isinstance(self.category, MemoryCategory):
            raise TypeError("category must be MemoryCategory")
        normalized_scope = self.scope.strip().lower()
        if not normalized_scope:
            raise ValueError("scope must not be blank")
        object.__setattr__(self, "scope", normalized_scope)
        if self.version <= 0:
            raise ValueError("version must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("memory timestamps must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.deleted_at is not None and self.deleted_at.tzinfo is None:
            raise ValueError("deleted_at must be timezone-aware")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

        if self.status is MemoryStatus.ACTIVE:
            if self.content is None or not self.content.strip():
                raise ValueError("active memory requires content")
            expected = memory_content_digest(self.content)
            if self.content_digest != expected:
                raise ValueError("content_digest does not match content")
            if self.deleted_at is not None:
                raise ValueError("active memory cannot have deleted_at")
        else:
            if self.content is not None:
                raise ValueError("tombstoned memory cannot retain content")
            if self.deleted_at is None:
                raise ValueError("tombstoned memory requires deleted_at")
