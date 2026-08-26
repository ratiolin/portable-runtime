from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import portable_runtime.stores.sqlite as sqlite_store_module
from portable_runtime.records.models import ChangeObjectRecord
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _seed_endpoints(store: Any, prefix: str) -> tuple[ChangeObjectRecord, ChangeObjectRecord]:
    left = ChangeObjectRecord(id=f"{prefix}_left", lifecycle_status="draft")
    right = ChangeObjectRecord(id=f"{prefix}_right", lifecycle_status="draft")
    store.save_record(left)
    store.save_record(right)
    return left, right


def _relation_ids(state: dict[str, list[dict[str, object]]]) -> set[str]:
    return {
        str(item["id"])
        for item in state.get("relation", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def test_memory_export_state_holds_one_lock_across_complete_snapshot_copy(monkeypatch) -> None:
    store = InMemoryStateStore()
    left, right = _seed_endpoints(store, "memory_coherence")
    relation = RecordRelation(
        id="memory_after_snapshot",
        relation_type="depends-on",
        subject_ref=left.id,
        object_ref=right.id,
    )

    entered_copy = threading.Event()
    release_copy = threading.Event()
    writer_started = threading.Event()
    writer_done = threading.Event()
    original_model_dump = BaseModel.model_dump

    def blocking_model_dump(self: BaseModel, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if threading.current_thread().name == "memory-eua-export" and not entered_copy.is_set():
            entered_copy.set()
            if not release_copy.wait(timeout=5):
                raise AssertionError("timed out while holding memory snapshot copy")
        return original_model_dump(self, *args, **kwargs)

    monkeypatch.setattr(BaseModel, "model_dump", blocking_model_dump)
    captured: dict[str, dict[str, list[dict[str, object]]]] = {}

    def export() -> None:
        captured["state"] = store.export_state()

    def write() -> None:
        writer_started.set()
        store.save_relation(relation)
        writer_done.set()

    exporter = threading.Thread(target=export, name="memory-eua-export")
    writer = threading.Thread(target=write, name="memory-eua-writer")
    exporter.start()
    assert entered_copy.wait(timeout=2)
    writer.start()
    assert writer_started.wait(timeout=2)
    # A writer cannot cross the snapshot while export_state is serializing.
    assert not writer_done.wait(timeout=0.1)
    release_copy.set()
    exporter.join(timeout=5)
    writer.join(timeout=5)

    assert not exporter.is_alive()
    assert not writer.is_alive()
    assert writer_done.is_set()
    assert relation.id not in _relation_ids(captured["state"])
    assert relation.id in _relation_ids(store.export_state())


def test_sqlite_export_state_materializes_one_statement_snapshot_before_parse(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SQLiteStateStore(tmp_path / "eua-coherence.sqlite3")
    try:
        left, right = _seed_endpoints(store, "sqlite_coherence")
        relation = RecordRelation(
            id="sqlite_after_snapshot",
            relation_type="depends-on",
            subject_ref=left.id,
            object_ref=right.id,
        )

        entered_parse = threading.Event()
        release_parse = threading.Event()
        writer_done = threading.Event()
        original_loads = sqlite_store_module.json.loads

        def blocking_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
            if threading.current_thread().name == "sqlite-eua-export" and not entered_parse.is_set():
                entered_parse.set()
                if not release_parse.wait(timeout=5):
                    raise AssertionError("timed out while parsing SQLite snapshot rows")
            return original_loads(value, *args, **kwargs)

        monkeypatch.setattr(sqlite_store_module.json, "loads", blocking_loads)
        captured: dict[str, dict[str, list[dict[str, object]]]] = {}

        def export() -> None:
            captured["state"] = store.export_state()

        def write() -> None:
            store.save_relation(relation)
            writer_done.set()

        exporter = threading.Thread(target=export, name="sqlite-eua-export")
        writer = threading.Thread(target=write, name="sqlite-eua-writer")
        exporter.start()
        assert entered_parse.wait(timeout=2)

        # export_state has already completed its single SELECT/fetchall under
        # the store lock. A later committed writer may run while those copied
        # rows are parsed, but it cannot appear in only part of that snapshot.
        writer.start()
        assert writer_done.wait(timeout=3)
        release_parse.set()
        exporter.join(timeout=5)
        writer.join(timeout=5)

        assert not exporter.is_alive()
        assert not writer.is_alive()
        assert relation.id not in _relation_ids(captured["state"])
        assert relation.id in _relation_ids(store.export_state())
    finally:
        store.close()
