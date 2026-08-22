from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

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
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import (
    ActionRecord,
    Assertion,
    BaseRecord,
    ChangeObjectRecord,
    Constraint,
    DecisionRecord,
    Derivation,
    EvidenceArtifact,
    Experiment,
    Goal,
    Observation,
    OutcomeRecord,
    PolicyRecord,
    RevisionRecord,
)
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


class StoreUnavailable(RuntimeError):  # noqa: N818 - stable public error name from the closure plan
    """The SQLite store could not complete an operation.

    A database/SQL failure is deliberately distinct from a normal conditional
    miss (for example, a stale CAS version or a lease owned by another worker).
    Callers that need fail-closed behaviour can handle this typed error without
    mistaking infrastructure failure for an ordinary conflict.
    """


class CASExecutionError(StoreUnavailable):
    """A CAS transaction failed for a reason other than version conflict."""


class LeaseExecutionError(StoreUnavailable):
    """A lease transaction failed for a reason other than an ownership miss."""


def _parse_utc(value: Any) -> datetime | None:
    """Parse a persisted timestamp as an aware UTC datetime.

    ``None`` means no expiry.  Malformed timestamps raise instead of being
    treated as expired: an unknown lease state must not silently become
    acquirable.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid persisted timestamp type: {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid persisted timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


_RECORD_MODELS: dict[str, type[BaseRecord]] = {
    "EvidenceArtifact": EvidenceArtifact,
    "Observation": Observation,
    "Assertion": Assertion,
    "Goal": Goal,
    "Constraint": Constraint,
    "Experiment": Experiment,
    "Decision": DecisionRecord,
    "Action": ActionRecord,
    "Outcome": OutcomeRecord,
    "Revision": RevisionRecord,
    "ChangeObject": ChangeObjectRecord,
    "Policy": PolicyRecord,
    "Derivation": Derivation,
}


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
        "knowledge_projection": KnowledgeProjection,
        "event": Event,
        "step": Step,
        "attempt": StepAttempt,
        "checkpoint": Checkpoint,
        "compensation": Compensation,
        "record": BaseRecord,
        "relation": RecordRelation,
    }
    # Kept as an attribute so a conformance test can deliberately inject a
    # malformed statement and verify that it raises a typed DB error.
    _CAS_UPDATE_SQL = (
        "UPDATE runtime_records SET data=?, created_at=? "
        "WHERE kind=? AND id=? "
        "AND CAST(json_extract(data, '$.version') AS INTEGER)=?"
    )
    # authorization added dynamically via import_state handling


    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = _safe_db_path(path)
        self._lock = threading.RLock()
        # A private in-process capability opened only by CompletionAuthority.
        # Direct terminal status writes must never be enough to close work.
        self._terminal_completion_depth = 0
        self._terminal_completion_refs: tuple[str, ...] | None = None
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
                "expires_at TEXT, heartbeat_at TEXT)"
            )
            # Databases created by an earlier development build included a
            # redundant NOT NULL ``version`` column.  Keep writes compatible
            # with those files while using the independent lease table as the
            # source of truth.
            self._lease_has_version_column = any(
                row["name"] == "version"
                for row in self._connection.execute("PRAGMA table_info(runtime_leases)").fetchall()
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

    def _save_checked(self, kind: str, value: Any) -> None:
        """Run every normal state mutation through the graph commit gate."""
        self._atomic_graph_save(kind, value)

    def _reject_unproven_terminal_write(self, kind: str, value: Any) -> None:
        status = getattr(value, "status", None)
        terminal = (kind == "run" and status == "succeeded") or (kind == "work" and status == "completed")
        if terminal and self._terminal_completion_depth <= 0:
            raise ValueError("terminal completion requires CompletionAuthority proof commit")
        if not terminal:
            return
        metadata = getattr(value, "metadata", {})
        refs = metadata.get("_completion_proof_refs") if isinstance(metadata, dict) else None
        if self._terminal_completion_refs is None or not isinstance(refs, list) or tuple(str(ref) for ref in refs) != self._terminal_completion_refs:
            raise ValueError("terminal completion requires bound verification proof refs")
        for ref in self._terminal_completion_refs:
            proof = self.get_record(ref)
            proof_metadata = getattr(proof, "metadata", None) if proof is not None else None
            proof_metadata_map: dict[str, Any] = proof_metadata if isinstance(proof_metadata, dict) else {}
            result = proof_metadata_map.get("verification_result")
            if (
                getattr(proof, "record_type", None) != "EvidenceArtifact"
                or getattr(proof, "kind", None) not in {"closed-verification", "verification-result", "task-objective-proof"}
                or not isinstance(result, dict)
                or str(result.get("result", "")).lower() != "pass"
            ):
                raise ValueError("terminal completion requires durable passing verification proofs")
            expected_work_id = getattr(value, "id", None) if kind == "work" else getattr(value, "work_id", None)
            if proof_metadata_map.get("work_id") != expected_work_id or (
                kind == "run" and proof_metadata_map.get("run_id") != getattr(value, "id", None)
            ):
                raise ValueError("terminal completion proof is not bound to this Work/Run")

    def _atomic_graph_save(self, kind: str, value: Any, validator: Any | None = None) -> None:
        """Validate the current graph and persist its delta in one transaction."""
        with self._lock:
            owns_transaction = not self._connection.in_transaction
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                if validator is not None:
                    validator()
                self._reject_unproven_terminal_write(kind, value)
                self._validate_candidate_write(kind, value)
                self._save(kind, value)
                if owns_transaction:
                    self._connection.execute("COMMIT")
            except Exception:
                if owns_transaction:
                    self._rollback(self._connection.cursor())
                raise

    @contextmanager
    def terminal_completion(self, verification_refs: list[str] | None = None):
        """Open the private capability used by CompletionAuthority only."""
        with self._lock:
            self._terminal_completion_depth += 1
            previous_refs = self._terminal_completion_refs
            self._terminal_completion_refs = tuple(verification_refs or ())
            try:
                yield self
            finally:
                self._terminal_completion_refs = previous_refs
                self._terminal_completion_depth -= 1

    def _validate_candidate_write(self, kind: str, value: Any) -> None:
        """Validate semantic writes against the complete current graph."""
        from portable_runtime.protocol.validation import assert_valid_candidate_write

        assert_valid_candidate_write(self.export_state(), kind, value)

    def _get(self, kind: str, value_type: type[Any], identifier: str) -> Any | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT data FROM runtime_records WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        if not row:
            return None
        if kind == "record":
            payload = json.loads(row["data"])
            model_type = _RECORD_MODELS.get(str(payload.get("record_type")), BaseRecord)
            return model_type.model_validate(payload)
        return value_type.model_validate_json(row["data"])

    def _list(self, kind: str, value_type: type[Any]) -> list[Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT data FROM runtime_records WHERE kind=? ORDER BY created_at DESC, id DESC", (kind,)
            ).fetchall()
        if kind == "record":
            values: list[BaseRecord] = []
            for row in rows:
                payload = json.loads(row["data"])
                model_type = _RECORD_MODELS.get(str(payload.get("record_type")), BaseRecord)
                values.append(model_type.model_validate(payload))
            return values
        return [value_type.model_validate_json(row["data"]) for row in rows]

    def save_work(self, value: Work) -> None: self._save_checked("work", value)
    def get_work(self, work_id: str) -> Work | None: return self._get("work", Work, work_id)
    def list_work(self, status: str | None = None) -> list[Work]:
        return [value for value in self._list("work", Work) if status is None or value.status == status]

    def save_run(self, value: Run) -> None: self._save_checked("run", value)
    def get_run(self, run_id: str) -> Run | None:
        # The lease table is authoritative.  Overlay its current state so a
        # stale run JSON mirror cannot make a caller believe an old owner is
        # still fencing the run.
        with self._lock:
            row = self._connection.execute(
                "SELECT data FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)
            ).fetchone()
            if row is None:
                return None
            lease = self._connection.execute(
                "SELECT owner, generation, expires_at, heartbeat_at "
                "FROM runtime_leases WHERE run_id=?",
                (run_id,),
            ).fetchone()
        run = Run.model_validate_json(row["data"])
        if lease is None:
            return run
        return run.model_copy(
            update={
                "lease_owner": lease["owner"],
                "lease_generation": int(lease["generation"]),
                "lease_expires_at": _parse_utc(lease["expires_at"]),
                "heartbeat_at": _parse_utc(lease["heartbeat_at"]),
            }
        )
    def list_runs(self, work_id: str | None = None) -> list[Run]:
        return [value for value in self._list("run", Run) if work_id is None or value.work_id == work_id]

    def save_artifact(self, value: Artifact) -> None: self._save_checked("artifact", value)
    def get_artifact(self, artifact_id: str) -> Artifact | None: return self._get("artifact", Artifact, artifact_id)
    def save_evidence(self, value: Evidence) -> None: self._save_checked("evidence", value)
    def get_evidence(self, evidence_id: str) -> Evidence | None: return self._get("evidence", Evidence, evidence_id)
    def list_evidence(self, subject_ref: str | None = None) -> list[Evidence]:
        values = self.list_raw_legacy_evidence(subject_ref)
        try:
            from portable_runtime.compat.legacy_records import evidence_artifact_to_legacy

            values.extend(
                converted
                for value in self.list_records("EvidenceArtifact")
                if isinstance(value, EvidenceArtifact)
                for converted in (evidence_artifact_to_legacy(value),)
                if subject_ref is None or subject_ref in converted.subject_refs
            )
        except Exception:
            pass
        return values

    def list_raw_legacy_evidence(self, subject_ref: str | None = None) -> list[Evidence]:
        return [
            value
            for value in self._list("evidence", Evidence)
            if subject_ref is None or subject_ref in value.subject_refs
        ]
    def save_decision(self, value: Decision) -> None: self._save_checked("decision", value)
    def get_decision(self, decision_id: str) -> Decision | None: return self._get("decision", Decision, decision_id)
    def save_action(self, value: Action) -> None: self._save_checked("action", value)
    def save_outcome(self, value: Outcome) -> None: self._save_checked("outcome", value)
    def save_knowledge(self, value: KnowledgeItem) -> None: self._save_checked("knowledge", value)
    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        legacy = self._get("knowledge", KnowledgeItem, knowledge_id)
        for projection in self._list("knowledge_projection", KnowledgeProjection):
            if projection.id == knowledge_id or projection.metadata.get("legacy_id") == knowledge_id:
                from portable_runtime.compat.legacy_records import knowledge_projection_to_legacy

                return knowledge_projection_to_legacy(projection)
        return legacy
    def list_knowledge(self, status: str | None = None) -> list[KnowledgeItem]:
        values = self.list_raw_legacy_knowledge(status)
        try:
            from portable_runtime.compat.legacy_records import knowledge_projection_to_legacy

            values.extend(
                knowledge_projection_to_legacy(value)
                for value in self._list("knowledge_projection", KnowledgeProjection)
                if status is None or value.lifecycle_status == status
            )
        except Exception:
            pass
        return values

    def list_raw_legacy_knowledge(self, status: str | None = None) -> list[KnowledgeItem]:
        return [value for value in self._list("knowledge", KnowledgeItem) if status is None or value.status == status]

    def save_knowledge_projection(self, value: KnowledgeProjection) -> None:
        self._atomic_graph_save("knowledge_projection", value)

    def get_knowledge_projection(self, projection_id: str) -> KnowledgeProjection | None:
        return self._get("knowledge_projection", KnowledgeProjection, projection_id)

    def list_knowledge_projections(self, status: str | None = None) -> list[KnowledgeProjection]:
        return [
            value
            for value in self._list("knowledge_projection", KnowledgeProjection)
            if status is None or value.lifecycle_status == status
        ]
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

    # R1.1 Execution Integrity
    def save_step(self, value: Step) -> None: self._save_checked("step", value)
    def get_step(self, step_id: str) -> Step | None: return self._get("step", Step, step_id)
    def list_steps(self, run_id: str | None = None) -> list[Step]:
        return [v for v in self._list("step", Step) if run_id is None or v.run_id == run_id]
    def list_stale_steps(self, before_seconds: float = 30) -> list[Step]:
        import datetime
        now = datetime.datetime.now(datetime.UTC)
        cutoff = now - datetime.timedelta(seconds=before_seconds)
        return [v for v in self._list("step", Step) if v.status == "running" and v.updated_at < cutoff]
    def save_attempt(self, value: StepAttempt) -> None: self._save_checked("attempt", value)
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: return self._get("attempt", StepAttempt, attempt_id)
    def list_attempts(self, step_id: str | None = None) -> list[StepAttempt]:
        return [v for v in self._list("attempt", StepAttempt) if step_id is None or v.step_id == step_id]
    def save_checkpoint(self, value: Checkpoint) -> None: self._save_checked("checkpoint", value)
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None: return self._get("checkpoint", Checkpoint, checkpoint_id)
    def save_compensation(self, value: Compensation) -> None: self._save_checked("compensation", value)

    @staticmethod
    def _rollback(cursor: sqlite3.Cursor) -> None:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            # The original operation is the useful diagnostic.  A rollback
            # failure must never turn an already typed error back into False.
            pass

    def compare_and_swap(self, kind: str, identifier: str, expected_version: int, new_value) -> bool:
        """Atomically replace a JSON record only at the expected version.

        ``False`` means the predicate matched zero rows (a normal stale/missing
        record conflict).  Any SQL/transaction failure raises
        :class:`CASExecutionError`; there is intentionally no permissive
        insert/upsert fallback.
        """

        data = new_value.model_dump(mode="json")
        raw = json.dumps(data, ensure_ascii=False)
        created_at = data.get("created_at", "") if isinstance(data, dict) else ""
        with self._lock:
            cur = self._connection.cursor()
            transaction_started = False
            try:
                cur.execute("BEGIN IMMEDIATE")
                transaction_started = True
                current_row = cur.execute(
                    "SELECT data FROM runtime_records WHERE kind=? AND id=?",
                    (kind, identifier),
                ).fetchone()
                if current_row is None:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                current_payload = json.loads(current_row["data"])
                current_version = int(current_payload.get("version", 0)) if isinstance(current_payload, dict) else 0
                if current_version != expected_version:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                # Validate against the same locked snapshot that the
                # conditional update will mutate.
                self._reject_unproven_terminal_write(kind, new_value)
                self._validate_candidate_write(kind, new_value)
                cur.execute(
                    self._CAS_UPDATE_SQL,
                    (raw, created_at, kind, identifier, expected_version),
                )
                if cur.rowcount == 0:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                if cur.rowcount != 1:
                    raise sqlite3.DatabaseError(f"CAS affected unexpected row count: {cur.rowcount}")
                cur.execute("COMMIT")
                transaction_started = False
                return True
            except ValueError:
                if transaction_started:
                    self._rollback(cur)
                raise
            except Exception as exc:
                if transaction_started:
                    self._rollback(cur)
                raise CASExecutionError(
                    f"SQLite CAS execution failed for {kind!r}/{identifier!r}"
                ) from exc
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
    def _insert_lease(
        self,
        cursor: sqlite3.Cursor,
        run_id: str,
        owner: str,
        generation: int,
        expires_at: str,
        heartbeat_at: str,
    ) -> None:
        if self._lease_has_version_column:
            cursor.execute(
                "INSERT INTO runtime_leases "
                "(run_id, owner, generation, expires_at, heartbeat_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, owner, generation, expires_at, heartbeat_at, generation),
            )
            return
        cursor.execute(
            "INSERT INTO runtime_leases "
            "(run_id, owner, generation, expires_at, heartbeat_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, owner, generation, expires_at, heartbeat_at),
        )

    @staticmethod
    def _load_run_payload(cursor: sqlite3.Cursor, run_id: str) -> tuple[dict[str, Any], str] | None:
        row = cursor.execute(
            "SELECT data, created_at FROM runtime_records WHERE kind=? AND id=?", ("run", run_id)
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["data"])
        if not isinstance(payload, dict):
            raise ValueError(f"run record {run_id!r} is not a JSON object")
        return payload, row["created_at"]

    @staticmethod
    def _mirror_run_lease(
        cursor: sqlite3.Cursor,
        run_id: str,
        *,
        owner: str | None,
        generation: int,
        expires_at: str | None,
        heartbeat_at: str | None,
    ) -> None:
        loaded = SQLiteStateStore._load_run_payload(cursor, run_id)
        if loaded is None:
            raise ValueError(f"run record disappeared while updating lease: {run_id!r}")
        payload, created_at = loaded
        payload["lease_owner"] = owner
        payload["lease_generation"] = generation
        payload["lease_expires_at"] = expires_at
        payload["heartbeat_at"] = heartbeat_at
        cursor.execute(
            "UPDATE runtime_records SET data=?, created_at=? WHERE kind=? AND id=?",
            (json.dumps(payload, ensure_ascii=False), payload.get("created_at") or created_at, "run", run_id),
        )

    def acquire_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        with self._lock:
            cur = self._connection.cursor()
            transaction_started = False
            try:
                cur.execute("BEGIN IMMEDIATE")
                transaction_started = True
                run_payload = self._load_run_payload(cur, run_id)
                if run_payload is None:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                lease_row = cur.execute(
                    "SELECT owner, generation, expires_at FROM runtime_leases WHERE run_id=?", (run_id,)
                ).fetchone()
                now = datetime.now(UTC)
                now_iso = now.isoformat()
                expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()
                if lease_row is None:
                    payload, _created_at = run_payload
                    current_owner = payload.get("lease_owner")
                    current_generation = int(payload.get("lease_generation") or 0)
                    current_expiry = _parse_utc(payload.get("lease_expires_at"))
                else:
                    current_owner = lease_row["owner"]
                    current_generation = int(lease_row["generation"])
                    current_expiry = _parse_utc(lease_row["expires_at"])

                # A different owner may take over only after a known expiry.
                # ``None``/malformed expiry is not treated as expired.
                if (
                    current_owner is not None
                    and current_owner != owner
                    and (current_expiry is None or current_expiry > now)
                ):
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False

                new_generation = current_generation + 1
                if lease_row is None:
                    self._insert_lease(cur, run_id, owner, new_generation, expires_iso, now_iso)
                else:
                    cur.execute(
                        "UPDATE runtime_leases SET owner=?, generation=?, expires_at=?, heartbeat_at=? "
                        "WHERE run_id=?",
                        (owner, new_generation, expires_iso, now_iso, run_id),
                    )
                    if cur.rowcount != 1:
                        raise sqlite3.DatabaseError("lease acquire updated an unexpected row count")
                self._mirror_run_lease(
                    cur,
                    run_id,
                    owner=owner,
                    generation=new_generation,
                    expires_at=expires_iso,
                    heartbeat_at=now_iso,
                )
                cur.execute("COMMIT")
                transaction_started = False
                return True
            except Exception as exc:
                if transaction_started:
                    self._rollback(cur)
                raise LeaseExecutionError(f"SQLite lease acquire failed for {run_id!r}") from exc

    def renew_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        with self._lock:
            cur = self._connection.cursor()
            transaction_started = False
            try:
                cur.execute("BEGIN IMMEDIATE")
                transaction_started = True
                lease_row = cur.execute(
                    "SELECT owner, generation, expires_at FROM runtime_leases WHERE run_id=?", (run_id,)
                ).fetchone()
                now = datetime.now(UTC)
                if lease_row is None or lease_row["owner"] != owner:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                current_expiry = _parse_utc(lease_row["expires_at"])
                if current_expiry is None or current_expiry <= now:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                if self._load_run_payload(cur, run_id) is None:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                now_iso = now.isoformat()
                expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()
                cur.execute(
                    "UPDATE runtime_leases SET expires_at=?, heartbeat_at=? "
                    "WHERE run_id=? AND owner=?",
                    (expires_iso, now_iso, run_id, owner),
                )
                if cur.rowcount != 1:
                    raise sqlite3.DatabaseError("lease renew updated an unexpected row count")
                self._mirror_run_lease(
                    cur,
                    run_id,
                    owner=owner,
                    generation=int(lease_row["generation"]),
                    expires_at=expires_iso,
                    heartbeat_at=now_iso,
                )
                cur.execute("COMMIT")
                transaction_started = False
                return True
            except Exception as exc:
                if transaction_started:
                    self._rollback(cur)
                raise LeaseExecutionError(f"SQLite lease renew failed for {run_id!r}") from exc

    def release_lease(self, run_id: str, owner: str) -> bool:
        with self._lock:
            cur = self._connection.cursor()
            transaction_started = False
            try:
                cur.execute("BEGIN IMMEDIATE")
                transaction_started = True
                lease_row = cur.execute(
                    "SELECT owner, generation FROM runtime_leases WHERE run_id=?", (run_id,)
                ).fetchone()
                if lease_row is None or lease_row["owner"] != owner:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                if self._load_run_payload(cur, run_id) is None:
                    cur.execute("ROLLBACK")
                    transaction_started = False
                    return False
                cur.execute(
                    "UPDATE runtime_leases SET owner=NULL, expires_at=NULL, heartbeat_at=NULL "
                    "WHERE run_id=? AND owner=?",
                    (run_id, owner),
                )
                if cur.rowcount != 1:
                    raise sqlite3.DatabaseError("lease release updated an unexpected row count")
                self._mirror_run_lease(
                    cur,
                    run_id,
                    owner=None,
                    generation=int(lease_row["generation"]),
                    expires_at=None,
                    heartbeat_at=None,
                )
                cur.execute("COMMIT")
                transaction_started = False
                return True
            except Exception as exc:
                if transaction_started:
                    self._rollback(cur)
                raise LeaseExecutionError(f"SQLite lease release failed for {run_id!r}") from exc

    # Records R1.2 implementation milestone
    def save_record(self, value: BaseRecord) -> None:
        try:
            from portable_runtime.records.authorization import AuthorizationGrant
            if isinstance(value, AuthorizationGrant):
                self.save_authorization(value)
                return
        except Exception:
            pass
        from portable_runtime.records.validation import validate_canonical_write, validate_record

        def validate() -> None:
            errs = [*validate_record(value), *validate_canonical_write(value)]
            if errs:
                raise ValueError("; ".join(errs))

        self._atomic_graph_save("record", value, validate)

    def get_record(self, record_id: str) -> BaseRecord | None:
        return self._get("record", BaseRecord, record_id)

    def list_records(self, record_type: str | None = None) -> list[BaseRecord]:
        vals = self._list("record", BaseRecord)
        return [v for v in vals if record_type is None or v.record_type == record_type]

    def save_relation(self, value: RecordRelation) -> None:
        from portable_runtime.records.relations import validate_relation
        def validate() -> None:
            errs = validate_relation(value)
            if errs:
                raise ValueError("; ".join(errs))

        self._atomic_graph_save("relation", value, validate)

    def get_relation(self, relation_id: str) -> RecordRelation | None:
        return self._get("relation", RecordRelation, relation_id)
    def save_authorization(self, value: Any) -> None:
        from portable_runtime.records.authorization import AuthorizationGrant, validate_grant
        def validate() -> None:
            if isinstance(value, AuthorizationGrant):
                errs = validate_grant(value)
                if errs:
                    raise ValueError("; ".join(errs))

        self._atomic_graph_save("authorization", value, validate)
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
        # Validate every incoming object and the merged graph before opening a
        # write transaction.  This prevents a malformed state import from
        # partially landing when the caller imports one bucket at a time.
        prepared: dict[str, list[BaseRecord]] = {}
        for kind, values in state.items():
            value_type = self._types.get(kind)
            if value_type is None and kind == "authorization":
                try:
                    from portable_runtime.records.authorization import AuthorizationGrant
                    value_type = AuthorizationGrant
                except Exception:
                    value_type = None
            if value_type is None:
                continue
            prepared[kind] = [cast(BaseRecord, value_type.model_validate(raw)) for raw in values]
        candidate = self.export_state()
        for kind, prepared_values in prepared.items():
            incoming_ids = {value.id for value in prepared_values}  # type: ignore[attr-defined]
            candidate[kind] = [
                raw for raw in candidate.get(kind, [])
                if isinstance(raw, dict) and raw.get("id") not in incoming_ids
            ] + [value.model_dump(mode="json") for value in prepared_values]
        from portable_runtime.protocol.validation import assert_valid_state_graph

        assert_valid_state_graph(candidate)
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                for kind, prepared_values in prepared.items():
                    for value in prepared_values:
                        self._connection.execute(
                            "INSERT INTO runtime_records(kind, id, data, created_at) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(kind, id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
                            (
                                kind,
                                value.id,  # type: ignore[attr-defined]
                                json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
                                value.created_at.isoformat(),  # type: ignore[attr-defined]
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





