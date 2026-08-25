"""F1-B3 outcome-governance impact substrate.

P1a resolves an ``OutcomeConfirmed`` journal event only when the complete
F1-B2 verified-outcome authority graph deterministically replays.  Event type
or payload claims alone never create B3 trigger authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.records.models import BaseRecord, OutcomeRecord
from portable_runtime.records.verified_outcome_commit import (
    PreparedVerifiedOutcomeCommit,
    VerifiedOutcomeCommitRequest,
    prepare_verified_outcome_commit,
    same_verified_outcome_semantics,
)

TriggerResolutionStatus = Literal["ready", "unavailable"]


class OutcomeConfirmedTriggerStore(Protocol):
    def get_event(self, event_id: str) -> Event | None: ...
    def get_record(self, record_id: str) -> object | None: ...
    def get_action(self, action_id: str) -> Action | None: ...
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: ...
    def get_step(self, step_id: str) -> Step | None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def get_work(self, work_id: str) -> Work | None: ...


@dataclass(frozen=True)
class OutcomeConfirmedTriggerResolution:
    status: TriggerResolutionStatus
    event_ref: str
    reason: str
    event: Event | None = None
    outcome: OutcomeRecord | None = None
    accepted_event: Event | None = None
    prepared: PreparedVerifiedOutcomeCommit | None = None

    @property
    def authoritative(self) -> bool:
        return self.status == "ready"


def _as_confirmed_outcome(value: object | None) -> OutcomeRecord | None:
    if isinstance(value, OutcomeRecord):
        outcome = value
    elif isinstance(value, BaseRecord) and value.record_type == "Outcome":
        try:
            outcome = OutcomeRecord.model_validate(value.model_dump(mode="python"))
        except Exception:
            return None
    else:
        return None
    return outcome if outcome.lifecycle_status == "confirmed" else None


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    values = tuple(item.strip() for item in value)
    return values if len(set(values)) == len(values) else None


def _commit_request_from_outcome(outcome: OutcomeRecord) -> VerifiedOutcomeCommitRequest | None:
    metadata = outcome.metadata if isinstance(outcome.metadata, dict) else {}
    work_id = metadata.get("work_id")
    run_id = metadata.get("run_id")
    request_id = metadata.get("request_id")
    attempt_ref = metadata.get("attempt_ref")
    verification_scope = metadata.get("verification_scope")
    subject_version_refs = _strings(metadata.get("subject_version_refs"))
    evidence_refs = tuple(ref.strip() for ref in outcome.evidence_refs if isinstance(ref, str) and ref.strip())
    if (
        not isinstance(work_id, str)
        or not work_id
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(request_id, str)
        or not request_id
        or not isinstance(attempt_ref, str)
        or not attempt_ref
        or not isinstance(verification_scope, dict)
        or subject_version_refs is None
        or not evidence_refs
        or len(set(evidence_refs)) != len(evidence_refs)
    ):
        return None
    return VerifiedOutcomeCommitRequest(
        action_ref=outcome.action_ref,
        evidence_refs=evidence_refs,
        expected_work_id=work_id,
        expected_run_id=run_id,
        expected_request_id=request_id,
        expected_attempt_ref=attempt_ref,
        verification_scope={str(key): value for key, value in verification_scope.items()},
        subject_version_refs=subject_version_refs,
    )


def resolve_outcome_confirmed_trigger(
    store: OutcomeConfirmedTriggerStore,
    event_id: str,
) -> OutcomeConfirmedTriggerResolution:
    """Resolve one journal event into an authoritative F1-B3 trigger.

    Resolution is read-only.  Failure never marks the event processed and never
    creates a review obligation.
    """

    event = store.get_event(event_id)
    if event is None:
        return OutcomeConfirmedTriggerResolution("unavailable", event_id, "event-missing")
    if event.type != "OutcomeConfirmed":
        return OutcomeConfirmedTriggerResolution("unavailable", event_id, "wrong-event-type", event=event)

    outcome = _as_confirmed_outcome(store.get_record(event.subject_ref))
    if outcome is None:
        return OutcomeConfirmedTriggerResolution(
            "unavailable", event_id, "confirmed-outcome-missing", event=event
        )
    request = _commit_request_from_outcome(outcome)
    if request is None:
        return OutcomeConfirmedTriggerResolution(
            "unavailable", event_id, "outcome-binding-incomplete", event=event, outcome=outcome
        )

    try:
        prepared = prepare_verified_outcome_commit(store, request)
    except Exception:
        return OutcomeConfirmedTriggerResolution(
            "unavailable", event_id, "authority-replay-failed", event=event, outcome=outcome
        )

    expected_accepted, expected_confirmed = prepared.events
    accepted = store.get_event(expected_accepted.id)
    if (
        prepared.outcome.id != outcome.id
        or expected_confirmed.id != event.id
        or accepted is None
        or not same_verified_outcome_semantics(outcome, prepared.outcome)
        or not same_verified_outcome_semantics(accepted, expected_accepted)
        or not same_verified_outcome_semantics(event, expected_confirmed)
    ):
        return OutcomeConfirmedTriggerResolution(
            "unavailable",
            event_id,
            "authority-graph-mismatch",
            event=event,
            outcome=outcome,
            accepted_event=accepted,
            prepared=prepared,
        )

    return OutcomeConfirmedTriggerResolution(
        "ready",
        event_id,
        "authoritative-outcome-confirmed",
        event=event,
        outcome=outcome,
        accepted_event=accepted,
        prepared=prepared,
    )


__all__ = [
    "OutcomeConfirmedTriggerResolution",
    "OutcomeConfirmedTriggerStore",
    "TriggerResolutionStatus",
    "resolve_outcome_confirmed_trigger",
]
