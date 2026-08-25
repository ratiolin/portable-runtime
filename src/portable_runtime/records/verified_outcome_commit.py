"""Store-owned construction contract for verification-authorized Outcomes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.records.models import OutcomeRecord
from portable_runtime.records.verification_binding import BoundVerificationEvidenceValidator


@dataclass(frozen=True)
class VerifiedOutcomeCommitRequest:
    """Caller-supplied binding expectations; never an Outcome declaration."""

    action_ref: str
    evidence_refs: tuple[str, ...]
    expected_work_id: str
    expected_run_id: str
    expected_request_id: str
    expected_attempt_ref: str
    verification_scope: dict[str, Any]
    subject_version_refs: tuple[str, ...]


@dataclass(frozen=True)
class PreparedVerifiedOutcomeCommit:
    outcome: OutcomeRecord
    events: tuple[Event, Event]
    binding_digest: str


class VerifiedOutcomeStoreReader(Protocol):
    def get_action(self, action_id: str) -> Action | None: ...
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: ...
    def get_step(self, step_id: str) -> Step | None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def get_work(self, work_id: str) -> Work | None: ...
    def get_record(self, record_id: str) -> object | None: ...


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _semantic_payload(value: object) -> dict[str, object]:
    dumper = getattr(value, "model_dump", None)
    if not callable(dumper):
        raise ValueError("verified-outcome replay requires typed persisted facts")
    payload = dict(dumper(mode="json"))
    payload.pop("created_at", None)
    return payload


def same_verified_outcome_semantics(left: object, right: object) -> bool:
    return _semantic_payload(left) == _semantic_payload(right)


def prepare_verified_outcome_commit(
    store: VerifiedOutcomeStoreReader,
    request: VerifiedOutcomeCommitRequest,
) -> PreparedVerifiedOutcomeCommit:
    """Re-read and validate the durable graph, then deterministically build authority facts."""

    evidence_refs = sorted({ref.strip() for ref in request.evidence_refs if ref.strip()})
    subject_versions = sorted({ref.strip() for ref in request.subject_version_refs if ref.strip()})
    if not evidence_refs:
        raise ValueError("verified-outcome commit requires evidence refs")
    if len(evidence_refs) != len(request.evidence_refs):
        raise ValueError("verified-outcome evidence refs must be non-empty and unique")
    if not subject_versions:
        raise ValueError("verified-outcome commit requires subject version refs")

    action = store.get_action(request.action_ref)
    attempt = store.get_attempt(request.expected_attempt_ref)
    if action is None or attempt is None:
        raise ValueError("verified-outcome commit requires durable Action and Attempt")
    step = store.get_step(attempt.step_id)
    run = store.get_run(request.expected_run_id)
    work = store.get_work(request.expected_work_id)
    if step is None or run is None or work is None:
        raise ValueError("verified-outcome commit requires complete Step/Run/Work graph")

    validated = BoundVerificationEvidenceValidator.validate(
        work=work,
        run=run,
        refs=evidence_refs,
        record_lookup=store.get_record,
        expected_scope=dict(request.verification_scope),
        expected_subject_version_refs=subject_versions,
        action=action,
        step=step,
        attempt=attempt,
        expected_request_id=request.expected_request_id,
        expected_attempt_ref=request.expected_attempt_ref,
        require_execution_binding=True,
        require_verifier_provenance=True,
    )

    obligation_refs: set[str] = set()
    artifact_refs: set[str] = set()
    verifier_provenance: list[dict[str, object]] = []
    for record in sorted(validated.records, key=lambda item: item.id):
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        obligation_refs.update(_string_list(metadata.get("obligation_refs")))
        artifact_refs.update(_string_list(metadata.get("artifact_refs")))
        provenance = metadata.get("verifier_provenance")
        if isinstance(provenance, dict):
            verifier_provenance.append({str(key): value for key, value in provenance.items()})

    binding_payload = {
        "action_ref": action.id,
        "evidence_refs": evidence_refs,
        "work_id": work.id,
        "run_id": run.id,
        "request_id": action.request_ref,
        "attempt_ref": attempt.id,
        "verification_scope": dict(request.verification_scope),
        "subject_version_refs": subject_versions,
        "objective_result": validated.objective_result,
    }
    binding_digest = _digest(binding_payload)
    outcome_id = f"outcome_verified_{binding_digest[:32]}"
    metadata = {
        "objective_result": validated.objective_result,
        "work_id": work.id,
        "run_id": run.id,
        "request_id": action.request_ref,
        "attempt_ref": attempt.id,
        "verification_scope": dict(request.verification_scope),
        "subject_version_refs": subject_versions,
        "obligation_refs": sorted(obligation_refs),
        "verifier_provenance": verifier_provenance,
        "verification_binding_digest": binding_digest,
    }
    outcome = OutcomeRecord(
        id=outcome_id,
        action_ref=action.id,
        evidence_refs=evidence_refs,
        artifact_refs=sorted(artifact_refs),
        lifecycle_status="confirmed",
        metadata=metadata,
    )
    event_payload = {
        "semantic_level": "objective-verification",
        "authoritative_outcome": True,
        "objective_result": validated.objective_result,
        "outcome_ref": outcome.id,
        "action_ref": action.id,
        "verification_refs": evidence_refs,
        "verification_binding_digest": binding_digest,
    }
    accepted = Event(
        id=f"event_objective_verification_{binding_digest[:32]}",
        type="ObjectiveVerificationAccepted",
        subject_ref=outcome.id,
        payload=event_payload,
    )
    confirmed = Event(
        id=f"event_outcome_confirmed_{binding_digest[:32]}",
        type="OutcomeConfirmed",
        subject_ref=outcome.id,
        payload=event_payload,
    )
    return PreparedVerifiedOutcomeCommit(outcome, (accepted, confirmed), binding_digest)
