from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

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


class InMemoryStateStore:
    """Deterministic store used by core tests and provider conformance tests."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, BaseModel]] = {
            "work": {},
            "run": {},
            "artifact": {},
            "evidence": {},
            "decision": {},
            "action": {},
            "outcome": {},
            "knowledge": {},
            "event": {},
            "step": {},
            "attempt": {},
            "checkpoint": {},
            "compensation": {},
            "record": {},
            "relation": {},
            "authorization": {},
        }
        self._leases: dict[str, dict[str, Any]] = {}

    def _save(self, kind: str, value: BaseModel) -> None:
        identifier = getattr(value, "id", None)
        if not isinstance(identifier, str):
            raise ValueError("runtime records require a string id")
        self._records[kind][identifier] = value

    def _get(self, kind: str, value_type: type[Any], identifier: str) -> Any | None:
        value = self._records[kind].get(identifier)
        return value if isinstance(value, value_type) else None

    def _list(self, kind: str, value_type: type[Any]) -> list[Any]:
        values = [value for value in self._records[kind].values() if isinstance(value, value_type)]
        return sorted(values, key=lambda value: value.created_at, reverse=True)

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

    def save_event(self, value: Event) -> None: self.append_event(value)

    def append_event(self, value: Event) -> None:
        existing = self._records.get("event", {}).get(value.id)
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
    def get_event(self, event_id: str) -> Event | None: return self._get("event", Event, event_id)
    def list_events(self, subject_ref: str | None = None) -> list[Event]:
        return [
            value
            for value in self._list("event", Event)
            if subject_ref is None or value.subject_ref == subject_ref
        ]

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
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        return self._get("checkpoint", Checkpoint, checkpoint_id)
    def save_compensation(self, value: Compensation) -> None: self._save("compensation", value)

    def compare_and_swap(self, kind: str, identifier: str, expected_version: int, new_value: Any) -> bool:
        existing = self._records.get(kind, {}).get(identifier)
        if existing is None:
            return False
        current_version = getattr(existing, "version", 0) if hasattr(existing, "version") else 0
        if current_version != expected_version:
            return False
        self._records[kind][identifier] = new_value
        return True

    @contextmanager
    def transaction(self):
        yield self

    def acquire_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        now = time.monotonic()
        existing = self._leases.get(run_id)
        if existing and existing["expires_at"] > now and existing["owner"] != owner:
            return False
        self._leases[run_id] = {"owner": owner, "expires_at": now + ttl_seconds, "generation": existing["generation"] + 1 if existing else 1}
        run = self.get_run(run_id)
        if run:
            run.lease_owner = owner
            run.lease_generation = self._leases[run_id]["generation"]
            import datetime
            run.lease_expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=ttl_seconds)
            self.save_run(run)
        return True

    def renew_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        existing = self._leases.get(run_id)
        if not existing or existing["owner"] != owner:
            return False
        existing["expires_at"] = time.monotonic() + ttl_seconds
        return True

    def release_lease(self, run_id: str, owner: str) -> bool:
        existing = self._leases.get(run_id)
        if not existing or existing["owner"] != owner:
            return False
        del self._leases[run_id]
        return True

    # Records V1.2
    def save_record(self, value: BaseRecord) -> None:
        # Gracefully handle AuthorizationGrant mis-routed via save_record (used in some tests)
        try:
            from portable_runtime.records.authorization import AuthorizationGrant
            if isinstance(value, AuthorizationGrant):
                # delegate to authorization bucket
                self.save_authorization(value)
                return
        except Exception:
            pass
        # validate orthogonal dimensions
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
    # Authorization (Bundle v2) — isolated from decision
    def save_authorization(self, value: Any) -> None:
        from portable_runtime.records.authorization import AuthorizationGrant
        if isinstance(value, AuthorizationGrant):
            from portable_runtime.records.authorization import validate_grant
            errs = validate_grant(value)
            # allow saving even if expired? validate only structural? For now raise only on missing fields via model validation already
            if any("principal_ref required" in e or "grantee_ref required" in e or "allowed_capabilities" in e for e in errs):
                raise ValueError("; ".join(errs))
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
        return {
            kind: [value.model_dump(mode="json") for value in values.values()]
            for kind, values in self._records.items()
        }

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        types: dict[str, type[Any]] = {
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
        # authorization handled separately
        try:
            from portable_runtime.records.authorization import AuthorizationGrant as _AuthGrant
            types["authorization"] = _AuthGrant
        except Exception:
            pass
        for kind, values in state.items():
            model_type = types.get(kind)
            if model_type is None:
                continue
            for raw in values:
                value = model_type.model_validate(raw)
                self._records[kind][value.id] = value

# noqa: E501 on long line handled





