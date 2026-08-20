from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from portable_runtime.core.models import (
    Action,
    Artifact,
    Decision,
    Event,
    Evidence,
    KnowledgeItem,
    Outcome,
    Run,
    Work,
)


class SQLiteStateStore:
    """Portable JSON-record store with stable IDs and atomic import/export."""

    _types: dict[str, type[Any]] = {
        "work": Work,
        "run": Run,
        "artifact": Artifact,
        "evidence": Evidence,
        "decision": Decision,
        "action": Action,
        "outcome": Outcome,
        "knowledge": KnowledgeItem,
        "event": Event,
    }

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)  # NOSONAR
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_records ("
                "kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, "
                "created_at TEXT NOT NULL, PRIMARY KEY(kind, id))"
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _save(self, kind: str, value: Any) -> None:
        data = value.model_dump(mode="json")
        with self._lock:
            self._connection.execute(
                "INSERT INTO runtime_records(kind, id, data, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(kind, id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
                (kind, value.id, json.dumps(data, ensure_ascii=False), data["created_at"]),
            )

    def _get(self, kind: str, value_type: type[Any], identifier: str) -> Any | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT data FROM runtime_records WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        return value_type.model_validate_json(row["data"]) if row else None

    def _list(self, kind: str, value_type: type[Any]) -> list[Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT data FROM runtime_records WHERE kind=? ORDER BY created_at DESC, id DESC", (kind,)
            ).fetchall()
        return [value_type.model_validate_json(row["data"]) for row in rows]

    def save_work(self, value: Work) -> None: self._save("work", value)
    def get_work(self, work_id: str) -> Work | None: return self._get("work", Work, work_id)
    def list_work(self, status: str | None = None) -> list[Work]:
        return [value for value in self._list("work", Work) if status is None or value.status == status]

    def save_run(self, value: Run) -> None: self._save("run", value)
    def get_run(self, run_id: str) -> Run | None: return self._get("run", Run, run_id)
    def list_runs(self, work_id: str | None = None) -> list[Run]:
        return [value for value in self._list("run", Run) if work_id is None or value.work_id == work_id]

    def save_artifact(self, value: Artifact) -> None: self._save("artifact", value)
    def get_artifact(self, artifact_id: str) -> Artifact | None: return self._get("artifact", Artifact, artifact_id)
    def save_evidence(self, value: Evidence) -> None: self._save("evidence", value)
    def list_evidence(self, subject_ref: str | None = None) -> list[Evidence]:
        return [
            value
            for value in self._list("evidence", Evidence)
            if subject_ref is None or subject_ref in value.subject_refs
        ]
    def save_decision(self, value: Decision) -> None: self._save("decision", value)
    def save_action(self, value: Action) -> None: self._save("action", value)
    def save_outcome(self, value: Outcome) -> None: self._save("outcome", value)
    def save_knowledge(self, value: KnowledgeItem) -> None: self._save("knowledge", value)
    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        return self._get("knowledge", KnowledgeItem, knowledge_id)
    def list_knowledge(self, status: str | None = None) -> list[KnowledgeItem]:
        return [value for value in self._list("knowledge", KnowledgeItem) if status is None or value.status == status]
    def append_event(self, value: Event) -> None: self._save("event", value)

    def export_state(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            rows = self._connection.execute("SELECT kind, data FROM runtime_records ORDER BY kind, id").fetchall()
        result: dict[str, list[dict[str, object]]] = {kind: [] for kind in self._types}
        for row in rows:
            result.setdefault(row["kind"], []).append(json.loads(row["data"]))
        return result

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                for kind, values in state.items():
                    value_type = self._types.get(kind)
                    if value_type is None:
                        continue
                    for raw in values:
                        value = value_type.model_validate(raw)
                        self._connection.execute(
                            "INSERT INTO runtime_records(kind, id, data, created_at) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(kind, id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
                            (
                                kind,
                                value.id,
                                json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
                                value.created_at.isoformat(),
                            ),
                        )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    # ---- bundle helpers (tar.zst with manifest + artifacts) ----

    def export_bundle(self, bundle_path: Path, artifact_store: Any | None = None, runtime_id: str = "runtime") -> Path:
        from .bundle import export_bundle as _export_bundle

        return _export_bundle(self, artifact_store, bundle_path, runtime_id=runtime_id)

    def import_bundle(self, bundle_path: Path, artifact_store: Any | None = None) -> dict[str, Any]:
        from .bundle import import_bundle as _import_bundle

        return _import_bundle(self, artifact_store, bundle_path)

