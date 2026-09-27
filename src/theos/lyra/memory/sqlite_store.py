from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from theos.lyra.memory.contracts import (
    MemoryCategory,
    MemoryRecord,
    MemoryStatus,
    memory_content_digest,
)

_SCHEMA_VERSION = 1


def default_memory_database_path() -> Path:
    override = os.environ.get("THEOS_MEMORY_DB")
    if override and override.strip():
        return Path(override).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "TheOS"
    else:
        base = Path.home() / ".theos"
    return (base / "storage" / "lyra-memory.sqlite3").resolve()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("persisted memory timestamp is not timezone-aware")
    return parsed


class SQLiteMemoryStore:
    """Small authoritative SQLite store for LYRA's first persistent-memory slice."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = default_memory_database_path() if path is None else Path(path).expanduser()
        self._path = self._path.resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def path(self) -> Path:
        return self._path

    def remember(
        self,
        content: str,
        *,
        category: MemoryCategory = MemoryCategory.PERSONAL,
        scope: str = "user",
        metadata: dict[str, str] | None = None,
        provenance: str = "user_explicit",
        expires_at: datetime | None = None,
    ) -> MemoryRecord:
        normalized = content.strip()
        if not normalized:
            raise ValueError("memory content must not be blank")
        if not isinstance(category, MemoryCategory):
            raise TypeError("category must be MemoryCategory")
        normalized_scope = scope.strip().lower()
        if not normalized_scope:
            raise ValueError("scope must not be blank")
        if expires_at is not None and expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")

        now = _utc_now()
        record = MemoryRecord(
            memory_id=uuid4(),
            category=category,
            scope=normalized_scope,
            content=normalized,
            content_digest=memory_content_digest(normalized),
            version=1,
            status=MemoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            metadata={} if metadata is None else metadata,
            provenance=provenance,
        )

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO memories (
                    memory_id, category, scope, content, content_digest,
                    version, status, created_at, updated_at, expires_at,
                    deleted_at, metadata_json, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.memory_id),
                    record.category.value,
                    record.scope,
                    record.content,
                    record.content_digest,
                    record.version,
                    record.status.value,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    None if record.expires_at is None else record.expires_at.isoformat(),
                    None,
                    json.dumps(dict(record.metadata), ensure_ascii=False, sort_keys=True),
                    record.provenance,
                ),
            )
        return record

    def read(self, memory_id: UUID) -> MemoryRecord | None:
        if not isinstance(memory_id, UUID):
            raise TypeError("memory_id must be UUID")
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (str(memory_id),),
            ).fetchone()
        if row is None:
            return None
        record = self._decode(row)
        if not self._visible(record, now=_utc_now()):
            return None
        return record

    def search(
        self,
        query: str,
        *,
        category: MemoryCategory | None = None,
        scope: str = "user",
        limit: int = 5,
    ) -> tuple[MemoryRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("memory query must not be blank")
        if category is not None and not isinstance(category, MemoryCategory):
            raise TypeError("category must be MemoryCategory or None")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        normalized_scope = scope.strip().lower()
        if not normalized_scope:
            raise ValueError("scope must not be blank")

        sql = """
            SELECT * FROM memories
            WHERE scope = ? AND status = 'active'
        """
        params: list[object] = [normalized_scope]
        if category is not None:
            sql += " AND category = ?"
            params.append(category.value)
        sql += " ORDER BY updated_at DESC, memory_id ASC LIMIT 1000"

        with closing(self._connect()) as connection, connection:
            rows = connection.execute(sql, params).fetchall()

        now = _utc_now()
        query_folded = normalized_query.casefold()
        terms = tuple(dict.fromkeys(query_folded.split()))
        scored: list[tuple[float, MemoryRecord]] = []

        for row in rows:
            record = self._decode(row)
            if not self._visible(record, now=now) or record.content is None:
                continue
            folded = record.content.casefold()
            score = float(sum(term in folded for term in terms))
            if query_folded in folded:
                score += 2.0
            if score <= 0:
                continue
            scored.append((score, record))

        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1].updated_at.timestamp(),
                item[1].memory_id.int,
            )
        )
        return tuple(record for _score, record in scored[:limit])

    def forget(self, memory_id: UUID) -> bool:
        current = self.read(memory_id)
        if current is None:
            return False
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE memories
                SET content = NULL,
                    metadata_json = '{}',
                    version = ?,
                    status = 'tombstoned',
                    updated_at = ?,
                    deleted_at = ?
                WHERE memory_id = ? AND status = 'active' AND version = ?
                """,
                (
                    current.version + 1,
                    now.isoformat(),
                    now.isoformat(),
                    str(memory_id),
                    current.version,
                ),
            )
        return cursor.rowcount == 1

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT schema_version FROM schema_meta WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(singleton, schema_version) VALUES (1, ?)",
                    (_SCHEMA_VERSION,),
                )
            elif int(row["schema_version"]) != _SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported LYRA memory schema version: {row['schema_version']}"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    content TEXT,
                    content_digest TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    status TEXT NOT NULL CHECK (status IN ('active', 'tombstoned')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    deleted_at TEXT,
                    metadata_json TEXT NOT NULL,
                    provenance TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_scope_category_status
                ON memories(scope, category, status, updated_at)
                """
            )

    @staticmethod
    def _visible(record: MemoryRecord, *, now: datetime) -> bool:
        if record.status is not MemoryStatus.ACTIVE:
            return False
        return record.expires_at is None or record.expires_at > now

    @staticmethod
    def _decode(row: sqlite3.Row) -> MemoryRecord:
        metadata_raw = json.loads(str(row["metadata_json"]))
        if not isinstance(metadata_raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in metadata_raw.items()
        ):
            raise ValueError("persisted memory metadata is invalid")
        content = row["content"]
        return MemoryRecord(
            memory_id=UUID(str(row["memory_id"])),
            category=MemoryCategory(str(row["category"])),
            scope=str(row["scope"]),
            content=None if content is None else str(content),
            content_digest=str(row["content_digest"]),
            version=int(row["version"]),
            status=MemoryStatus(str(row["status"])),
            created_at=_parse_datetime(str(row["created_at"])) or _utc_now(),
            updated_at=_parse_datetime(str(row["updated_at"])) or _utc_now(),
            expires_at=_parse_datetime(
                None if row["expires_at"] is None else str(row["expires_at"])
            ),
            deleted_at=_parse_datetime(
                None if row["deleted_at"] is None else str(row["deleted_at"])
            ),
            metadata=metadata_raw,
            provenance=str(row["provenance"]),
        )
