from __future__ import annotations

from theos.lyra.memory.contracts import MemoryCategory
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


def test_memory_persists_across_store_instances(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"

    first = SQLiteMemoryStore(path)
    created = first.remember(
        "Meu editor principal é o VS Code.",
        category=MemoryCategory.PERSONAL,
    )

    second = SQLiteMemoryStore(path)
    loaded = second.read(created.memory_id)
    results = second.search("editor")

    assert loaded is not None
    assert loaded.content == "Meu editor principal é o VS Code."
    assert [record.memory_id for record in results] == [created.memory_id]


def test_forgotten_memory_is_not_returned(tmp_path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    created = store.remember("Meu projeto atual é o The OS.")

    assert store.forget(created.memory_id) is True
    assert store.read(created.memory_id) is None
    assert store.search("The OS") == ()

def test_sqlite_file_handle_is_released(tmp_path) -> None:
    path = tmp_path / "releasable.sqlite3"
    store = SQLiteMemoryStore(path)
    record = store.remember("handle release probe")

    assert store.read(record.memory_id) is not None
    assert store.search("handle") != ()

    path.unlink()
    assert not path.exists()
