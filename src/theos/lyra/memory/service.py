from __future__ import annotations

from uuid import UUID

from theos.lyra.memory.contracts import MemoryCategory, MemoryRecord
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


class MemoryService:
    """LYRA-facing memory service. Writes are explicit; normal chat is not auto-persisted."""

    def __init__(self, store: SQLiteMemoryStore) -> None:
        if not isinstance(store, SQLiteMemoryStore):
            raise TypeError("store must be SQLiteMemoryStore")
        self._store = store

    @property
    def database_path(self):
        return self._store.path

    def remember(
        self,
        content: str,
        *,
        category: MemoryCategory = MemoryCategory.PERSONAL,
        scope: str = "user",
    ) -> MemoryRecord:
        return self._store.remember(
            content,
            category=category,
            scope=scope,
            provenance="user_explicit",
        )

    def recall(
        self,
        query: str,
        *,
        category: MemoryCategory | None = None,
        scope: str = "user",
        limit: int = 5,
    ) -> tuple[MemoryRecord, ...]:
        return self._store.search(
            query,
            category=category,
            scope=scope,
            limit=limit,
        )

    def forget(self, memory_id: UUID) -> bool:
        return self._store.forget(memory_id)
