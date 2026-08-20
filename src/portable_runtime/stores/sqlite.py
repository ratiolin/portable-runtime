from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from portable_runtime.core.models import (
    Action,
    Artifact,
    Checkpoint,
    Compensation,
    Decision,
    Event,
    Evidence,
    KnowledgeItem,
    Outcome,
    Run,
    Step,
    StepAttempt,
    Work,
)
from portable_runtime.records.models import BaseRecord
from portable_runtime.records.relations import RecordRelation


def _safe_db_path(p: Path) -> Path:
    if not str(p).strip():
        raise ValueError("db path must not be empty")
    if ".." in p.parts:
        cwd = Path.cwd().resolve()
        resolved = p.resolve()
        if not (resolved.is_relative_to(cwd) or resolved.is_relative_to(cwd.parent)):
            raise ValueError(f"db path escapes allowed base: {p}")
    return p


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
        "step": Step,
        "attempt": StepAttempt,
        "checkpoint": Checkpoint,
        "compensation": Compensation,
        "record": BaseRecord,
        "relation": RecordRelation,
    }
    # authorization added dynamically via import_state handling


    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = _safe_db_path(path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(_safe_db_path(path), check_same_thread=False, isolation_level=None)  # NOSONAR  # noqa: E501
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_records ("
                "kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, "
                "created_at TEXT NOT NULL, PRIMARY KEY(kind, id))"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS runtime_leases ("
                "run_id TEXT PRIMARY KEY, owner TEXT, generation INTEGER NOT NULL, "
                "expires_at TEXT, heartbeat_at TEXT, version INTEGER NOT NULL)"
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
    def get_evidence(self, evidence_id: str) -> Evidence | None: return self._get("evidence", Evidence, evidence_id)
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
    def append_event(self, value: Event) -> None:
        existing = self._get("event", Event, value.id)
        if existing is not None:
            try:
                ex = existing.model_dump(mode="json").copy()
                val = value.model_dump(mode="json").copy()
                ex.pop("created_at", None)
                val.pop("created_at", None)
                if ex == val:
                    return
            except Exception:
                pass
            raise ValueError(f"event journal is append-only: refusing to overwrite event {value.id!r}")
        self._save("event", value)
    def save_event(self, value: Event) -> None: self.append_event(value)
    def get_event(self, event_id: str) -> Event | None: return self._get("event", Event, event_id)
    def list_events(self, subject_ref: str | None = None) -> list[Event]:
        return [
            value
            for value in self._list("event", Event)
            if subject_ref is None or value.subject_ref == subject_ref
        ]

    # V1.1 Execution Integrity
    def save_step(self, value: Step) -> None: self._save("step", value)
    def get_step(self, step_id: str) -> Step | None: return self._get("step", Step, step_id)
    def list_steps(self, run_id: str | None = None) -> list[Step]:
        return [v for v in self._list("step", Step) if run_id is None or v.run_id == run_id]
    def list_stale_steps(self, before_seconds: float = 30) -> list[Step]:
        import datetime
        now = datetime.datetime.now(datetime.UTC)
        cutoff = now - datetime.timedelta(seconds=before_seconds)
        return [v for v in self._list("step", Step) if v.status == "running" and v.updated_at < cutoff]
    def save_attempt(self, value: StepAttempt) -> None: self._save("attempt", value)
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: return self._get("attempt", StepAttempt, attempt_id)
    def list_attempts(self, step_id: str | None = None) -> list[StepAttempt]:
        return [v for v in self._list("attempt", StepAttempt) if step_id is None or v.step_id == step_id]
    def save_checkpoint(self, value: Checkpoint) -> None: self._save("checkpoint", value)
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None: return self._get("checkpoint", Checkpoint, checkpoint_id)
    def save_compensation(self, value: Compensation) -> None: self._save("compensation", value)
    def compare_and_swap(self, kind: str, identifier: str, expected_version: int, new_value) -> bool:
        import json as _json

        data = new_value.model_dump(mode="json")
        raw = _json.dumps(data, ensure_ascii=False)
        created_at = data.get("created_at", "") if isinstance(data, dict) else ""
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                cur.execute(
                    "UPDATE runtime_records SET data=?, created_at=? WHERE kind=? AND id=? AND CAST(json_extract(data, '$.version') AS INTEGER)=?",
                    (raw, created_at, kind, identifier, expected_version),
                )
                if cur.rowcount != 1:
                    cur.execute("ROLLBACK")
                    return False
                cur.execute("COMMIT")
                return True
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                return False
    def transaction(self):
        from contextlib import contextmanager
        @contextmanager
        def _tx():
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    yield self
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
        return _tx()
    def acquire_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        import datetime
        import json as _json2
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                row = cur.execute("SELECT data FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)).fetchone()
                if row is None:
                    cur.execute("ROLLBACK")
                    return False
                lease_row = cur.execute("SELECT owner, generation, expires_at FROM runtime_leases WHERE run_id=?", (run_id,)).fetchone()
                now = datetime.datetime.now(datetime.UTC)
                now_iso = now.isoformat()
                expires_iso = (now + datetime.timedelta(seconds=ttl_seconds)).isoformat()
                if lease_row is not None:
                    exp_raw = lease_row["expires_at"]
                    gen = int(lease_row["generation"] or 0)
                    try:
                        exp_dt = datetime.datetime.fromisoformat(exp_raw) if isinstance(exp_raw, str) else None
                        if exp_dt is not None and exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        exp_dt = None
                    if lease_row["owner"] != owner and exp_dt is not None and exp_dt > now:
                        cur.execute("ROLLBACK")
                        return False
                    new_gen = gen + 1
                    cur.execute(
                        "INSERT INTO runtime_leases(run_id, owner, generation, expires_at, heartbeat_at, version) VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET owner=excluded.owner, generation=excluded.generation, expires_at=excluded.expires_at, heartbeat_at=excluded.heartbeat_at, version=excluded.version",
                        (run_id, owner, new_gen, expires_iso, now_iso, new_gen),
                    )
                else:
                    try:
                        data = _json2.loads(row["data"]) if isinstance(row["data"], str) else {}
                        cur_gen = int(data.get("lease_generation") or 0)
                        cur_owner = data.get("lease_owner")
                        cur_exp_raw = data.get("lease_expires_at")
                    except Exception:
                        cur_gen = 0
                        cur_owner = None
                        cur_exp_raw = None
                    if cur_owner and cur_owner != owner and cur_exp_raw:
                        try:
                            cur_exp = datetime.datetime.fromisoformat(cur_exp_raw) if isinstance(cur_exp_raw, str) else None
                            if cur_exp is not None and cur_exp.tzinfo is None:
                                cur_exp = cur_exp.replace(tzinfo=datetime.timezone.utc)
                            if cur_exp is not None and cur_exp > now:
                                cur.execute("ROLLBACK")
                                return False
                        except Exception:
                            pass
                    new_gen = cur_gen + 1
                    cur.execute(
                        "INSERT INTO runtime_leases(run_id, owner, generation, expires_at, heartbeat_at, version) VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET owner=excluded.owner, generation=excluded.generation, expires_at=excluded.expires_at, heartbeat_at=excluded.heartbeat_at, version=excluded.version",
                        (run_id, owner, new_gen, expires_iso, now_iso, new_gen),
                    )
                cur_row = cur.execute("SELECT data, created_at FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)).fetchone()
                if cur_row is not None:
                    try:
                        rd = _json2.loads(cur_row["data"])
                    except Exception:
                        rd = {}
                    rd["lease_owner"] = owner
                    rd["lease_generation"] = new_gen
                    rd["lease_expires_at"] = expires_iso
                    rd["heartbeat_at"] = now_iso
                    raw = _json2.dumps(rd, ensure_ascii=False)
                    created_at = rd.get("created_at") or cur_row["created_at"] or now_iso
                    cur.execute("UPDATE runtime_records SET data=?, created_at=? WHERE kind=? AND id=?", (raw, created_at, "run", run_id))
                cur.execute("COMMIT")
                return True
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                return False

    def renew_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        import datetime
        import json as _json2
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                lease_row = cur.execute("SELECT owner, generation, expires_at FROM runtime_leases WHERE run_id=?", (run_id,)).fetchone()
                now = datetime.datetime.now(datetime.UTC)
                if lease_row is None or lease_row["owner"] != owner:
                    cur.execute("ROLLBACK")
                    return False
                try:
                    exp_dt = datetime.datetime.fromisoformat(lease_row["expires_at"]) if isinstance(lease_row["expires_at"], str) else None
                    if exp_dt is not None and exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
                    if exp_dt is not None and exp_dt <= now:
                        cur.execute("ROLLBACK")
                        return False
                except Exception:
                    pass
                expires_iso = (now + datetime.timedelta(seconds=ttl_seconds)).isoformat()
                now_iso = now.isoformat()
                cur.execute("UPDATE runtime_leases SET expires_at=?, heartbeat_at=? WHERE run_id=?", (expires_iso, now_iso, run_id))
                cur_row = cur.execute("SELECT data, created_at FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)).fetchone()
                if cur_row is not None:
                    try:
                        rd = _json2.loads(cur_row["data"])
                    except Exception:
                        rd = {}
                    if rd.get("lease_owner") != owner:
                        cur.execute("ROLLBACK")
                        return False
                    rd["lease_expires_at"] = expires_iso
                    rd["heartbeat_at"] = now_iso
                    raw = _json2.dumps(rd, ensure_ascii=False)
                    created_at = rd.get("created_at") or cur_row["created_at"] or now_iso
                    cur.execute("UPDATE runtime_records SET data=?, created_at=? WHERE kind=? AND id=?", (raw, created_at, "run", run_id))
                cur.execute("COMMIT")
                return True
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                return False

    def release_lease(self, run_id: str, owner: str) -> bool:
        import datetime
        import json as _json2
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                lease_row = cur.execute("SELECT owner FROM runtime_leases WHERE run_id=?", (run_id,)).fetchone()
                if lease_row is None or lease_row["owner"] != owner:
                    cur.execute("ROLLBACK")
                    return False
                cur.execute("DELETE FROM runtime_leases WHERE run_id=?", (run_id,))
                cur_row = cur.execute("SELECT data, created_at FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)).fetchone()
                if cur_row is not None:
                    try:
                        rd = _json2.loads(cur_row["data"])
                    except Exception:
                        rd = {}
                    if rd.get("lease_owner") != owner:
                        cur.execute("ROLLBACK")
                        return False
                    rd["lease_owner"] = None
                    raw = _json2.dumps(rd, ensure_ascii=False)
                    created_at = rd.get("created_at") or cur_row["created_at"] or ""
                    cur.execute("UPDATE runtime_records SET data=?, created_at=? WHERE kind=? AND id=?", (raw, created_at, "run", run_id))
                cur.execute("COMMIT")
                return True
            except Exception:
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass
                return False

    # Records V1.2
    def save_record(self, value: BaseRecord) -> None:
        try:
            from portable_runtime.records.authorization import AuthorizationGrant
            if isinstance(value, AuthorizationGrant):
                self.save_authorization(value)
                return
        except Exception:
            pass
        from portable_runtime.records.validation import validate_record
        errs = validate_record(value)
        if errs:
            raise ValueError("; ".join(errs))
        self._save("record", value)

    def get_record(self, record_id: str) -> BaseRecord | None:
        return self._get("record", BaseRecord, record_id)

    def list_records(self, record_type: str | None = None) -> list[BaseRecord]:
        vals = self._list("record", BaseRecord)
        return [v for v in vals if record_type is None or v.record_type == record_type]

    def save_relation(self, value: RecordRelation) -> None:
        from portable_runtime.records.relations import validate_relation
        errs = validate_relation(value)
        if errs:
            raise ValueError("; ".join(errs))
        self._save("relation", value)

    def get_relation(self, relation_id: str) -> RecordRelation | None:
        return self._get("relation", RecordRelation, relation_id)
    def save_authorization(self, value: Any) -> None:
        # structural validation delegated to model
        self._save("authorization", value)
    def get_authorization(self, auth_id: str) -> Any | None:
        from portable_runtime.records.authorization import AuthorizationGrant
        return self._get("authorization", AuthorizationGrant, auth_id)
    def list_authorizations(self) -> list[Any]:
        from portable_runtime.records.authorization import AuthorizationGrant
        return self._list("authorization", AuthorizationGrant)

    def list_relations(self, relation_type: str | None = None) -> list[RecordRelation]:
        vals = self._list("relation", RecordRelation)
        return [v for v in vals if relation_type is None or v.relation_type == relation_type]

    def export_state(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            rows = self._connection.execute("SELECT kind, data FROM runtime_records ORDER BY kind, id").fetchall()
        # ensure authorization bucket exists even if _types not yet contains it
        try:
            from portable_runtime.records.authorization import AuthorizationGrant as _AG3  # noqa: N814
            if "authorization" not in self._types:
                self._types["authorization"] = _AG3
        except Exception:
            pass
        result: dict[str, list[dict[str, object]]] = {kind: [] for kind in self._types}
        for row in rows:
            result.setdefault(row["kind"], []).append(json.loads(row["data"]))
        return result

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        # lazily ensure authorization type is known
        if "authorization" not in self._types:
            try:
                from portable_runtime.records.authorization import AuthorizationGrant as _AG  # noqa: N814
                self._types["authorization"] = _AG
            except Exception:
                pass
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                for kind, values in state.items():
                    value_type = self._types.get(kind)
                    if value_type is None:
                        # try dynamic for authorization
                        if kind == "authorization":
                            try:
                                from portable_runtime.records.authorization import (
                                    AuthorizationGrant as _AG2,  # noqa: N814
                                )
                                value_type = _AG2
                            except Exception:  # noqa: S112
                                continue
                        else:
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

    def export_bundle(self, bundle_path: Path, artifact_store: Any | None = None, runtime_id: str = "runtime") -> Path:
        from .bundle import export_bundle as _export_bundle
        return _export_bundle(self, artifact_store, bundle_path, runtime_id=runtime_id)

    def import_bundle(self, bundle_path: Path, artifact_store: Any | None = None) -> dict[str, Any]:
        from .bundle import import_bundle as _import_bundle
        return _import_bundle(self, artifact_store, bundle_path)





