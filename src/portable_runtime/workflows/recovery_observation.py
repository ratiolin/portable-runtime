"""Durable execution-level observations for ambiguous committed dispatches.

A RecoveryObservation is not objective Outcome authority and is not a
recovery decision. The store re-derives its execution binding from the
exact InvocationDispatchCommitted graph before recording one observation
instance.

Legacy observations are dispatch-bound execution facts. Application-bound
observations additionally name one exact RecoveryApplication and may serve
as the durable completion fact for that one reconciliation responsibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from portable_runtime.core.models import Action, Event, Step, StepAttempt
from portable_runtime.governance.dispatch import dispatch_commit_identity_from_payload

RECOVERY_OBSERVATION_EVENT = "RecoveryObservationRecorded"
RECOVERY_OBSERVATION_SCHEMA = "recovery-observation-v1"
RECOVERY_APPLICATION_OBSERVATION_ROLE = "reconciliation-application-completion"
DISPATCH_COMMIT_EVENT = "InvocationDispatchCommitted"
DISPATCH_COMMIT_SCHEMA = "governance-dispatch-commit-v1"

RecoveryReportedStatus = Literal[
    "reported-succeeded",
    "reported-failed",
    "reported-unknown",
]
_REPORTED_STATUSES = frozenset(
    {"reported-succeeded", "reported-failed", "reported-unknown"}
)


@dataclass(frozen=True)
class RecoveryObservationCommitRequest:
    """Caller claim identifying one observation instance of one dispatch."""

    observation_instance_ref: str
    dispatch_commit_ref: str
    observation_source: str
    reported_status: RecoveryReportedStatus
    provenance_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryObservation:
    """Durable execution-level fact; never objective or recovery authority."""

    id: str
    observation_instance_ref: str
    dispatch_commit_ref: str
    action_ref: str
    attempt_ref: str
    step_ref: str
    request_ref: str
    provider_id: str
    idempotency_key: str | None
    observation_source: str
    reported_status: RecoveryReportedStatus
    provenance_refs: tuple[str, ...]
    recovery_application_ref: str | None = None
    durable: bool = True
    authoritative_outcome: bool = False


@dataclass(frozen=True)
class PreparedRecoveryObservationCommit:
    observation: RecoveryObservation
    event: Event


class RecoveryObservationStoreReader(Protocol):
    def get_event(self, event_id: str) -> Event | None: ...
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: ...
    def get_step(self, step_id: str) -> Step | None: ...
    def get_action(self, action_id: str) -> Action | None: ...


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"recovery observation requires dispatch {key}")
    return value


def _required_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"recovery observation requires {label}")
    return value.strip()


def recovery_application_observation_instance_ref(recovery_application_ref: str) -> str:
    """Derive the non-caller-controlled observation instance ref for one application."""

    application_ref = _required_ref(recovery_application_ref, "recovery_application_ref")
    return f"recovery_application_completion:{application_ref}"


def recovery_application_observation_identity(recovery_application_ref: str) -> str:
    """Derive one stable completion-observation identity for one application."""

    application_ref = _required_ref(recovery_application_ref, "recovery_application_ref")
    identity = {
        "schema": RECOVERY_OBSERVATION_SCHEMA,
        "semantic_role": RECOVERY_APPLICATION_OBSERVATION_ROLE,
        "recovery_application_ref": application_ref,
    }
    return f"recovery_observation_{_digest(identity)[:32]}"


def _dispatch_commit_ref(payload: dict[str, Any]) -> str:
    return dispatch_commit_identity_from_payload(payload)


def reported_status_from_capability_status(status: str) -> RecoveryReportedStatus:
    if status == "succeeded":
        return "reported-succeeded"
    if status == "failed":
        return "reported-failed"
    return "reported-unknown"


def _semantic_payload(value: object) -> dict[str, object]:
    dumper = getattr(value, "model_dump", None)
    if not callable(dumper):
        raise ValueError("recovery observation replay requires typed event facts")
    payload = dict(dumper(mode="json"))
    payload.pop("created_at", None)
    return payload


def same_recovery_observation_semantics(left: object, right: object) -> bool:
    return _semantic_payload(left) == _semantic_payload(right)


def recovery_observation_from_event(event: Event) -> RecoveryObservation:
    if event.type != RECOVERY_OBSERVATION_EVENT:
        raise ValueError("event is not a RecoveryObservationRecorded fact")
    payload = event.payload if isinstance(event.payload, dict) else {}
    if payload.get("schema") != RECOVERY_OBSERVATION_SCHEMA:
        raise ValueError("unsupported recovery observation schema")
    if payload.get("semantic_level") != "recovery-observation":
        raise ValueError("recovery observation semantic level mismatch")
    if payload.get("authoritative_outcome") is not False:
        raise ValueError("RecoveryObservation cannot claim objective authority")
    reported_status = payload.get("reported_status")
    if reported_status not in _REPORTED_STATUSES:
        raise ValueError("invalid recovery observation reported status")
    provenance_raw = payload.get("provenance_refs", [])
    if not isinstance(provenance_raw, list) or not all(
        isinstance(ref, str) and ref for ref in provenance_raw
    ):
        raise ValueError("invalid recovery observation provenance refs")
    idempotency_key = payload.get("idempotency_key")
    if idempotency_key is not None and not isinstance(idempotency_key, str):
        raise ValueError("invalid recovery observation idempotency key")

    instance_ref = _required_string(payload, "observation_instance_ref")
    application_ref_raw = payload.get("recovery_application_ref")
    observation_role = payload.get("observation_role")
    application_ref: str | None
    if application_ref_raw is None:
        if observation_role is not None:
            raise ValueError("legacy RecoveryObservation cannot claim application completion role")
        application_ref = None
    else:
        application_ref = _required_ref(
            application_ref_raw,
            "recovery_application_ref",
        )
        if observation_role != RECOVERY_APPLICATION_OBSERVATION_ROLE:
            raise ValueError("application-bound RecoveryObservation role mismatch")
        expected_instance_ref = recovery_application_observation_instance_ref(application_ref)
        if instance_ref != expected_instance_ref:
            raise ValueError("application-bound RecoveryObservation instance identity mismatch")
        expected_id = recovery_application_observation_identity(application_ref)
        if event.id != expected_id or event.subject_ref != application_ref:
            raise ValueError("application-bound RecoveryObservation deterministic identity mismatch")

    return RecoveryObservation(
        id=event.id,
        observation_instance_ref=instance_ref,
        dispatch_commit_ref=_required_string(payload, "dispatch_commit_ref"),
        action_ref=_required_string(payload, "action_ref"),
        attempt_ref=_required_string(payload, "attempt_ref"),
        step_ref=_required_string(payload, "step_ref"),
        request_ref=_required_string(payload, "request_ref"),
        provider_id=_required_string(payload, "provider_id"),
        idempotency_key=idempotency_key,
        observation_source=_required_string(payload, "observation_source"),
        reported_status=cast(RecoveryReportedStatus, reported_status),
        provenance_refs=tuple(provenance_raw),
        recovery_application_ref=application_ref,
    )


def prepare_recovery_observation_commit(
    store: RecoveryObservationStoreReader,
    request: RecoveryObservationCommitRequest,
) -> PreparedRecoveryObservationCommit:
    """Re-read a committed dispatch graph and build one observation fact."""

    instance_ref = request.observation_instance_ref.strip()
    dispatch_ref = request.dispatch_commit_ref.strip()
    source = request.observation_source.strip()
    if not instance_ref or not dispatch_ref or not source:
        raise ValueError(
            "recovery observation requires instance, dispatch, and source refs"
        )
    if request.reported_status not in _REPORTED_STATUSES:
        raise ValueError("invalid recovery observation reported status")
    provenance = tuple(
        sorted({ref.strip() for ref in request.provenance_refs if ref.strip()})
    )
    if len(provenance) != len(request.provenance_refs):
        raise ValueError(
            "recovery observation provenance refs must be non-empty and unique"
        )

    dispatch = store.get_event(dispatch_ref)
    if dispatch is None or dispatch.type != DISPATCH_COMMIT_EVENT:
        raise ValueError(
            "recovery observation requires exact InvocationDispatchCommitted event"
        )
    payload = dispatch.payload if isinstance(dispatch.payload, dict) else {}
    if payload.get("schema") != DISPATCH_COMMIT_SCHEMA:
        raise ValueError("recovery observation dispatch schema mismatch")
    if payload.get("linearization_domain") != "authoritative-state-store":
        raise ValueError(
            "recovery observation dispatch linearization domain mismatch"
        )
    if _dispatch_commit_ref(payload) != dispatch.id or dispatch.id != dispatch_ref:
        raise ValueError(
            "recovery observation dispatch deterministic identity mismatch"
        )

    request_ref = _required_string(payload, "request_id")
    provider_id = _required_string(payload, "provider_id")
    attempt_ref = _required_string(payload, "attempt_ref")
    if dispatch.subject_ref != request_ref:
        raise ValueError("recovery observation dispatch subject binding mismatch")
    attempt = store.get_attempt(attempt_ref)
    if attempt is None:
        raise ValueError("recovery observation requires durable StepAttempt")
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    if metadata.get("dispatch_commit_ref") != dispatch_ref:
        raise ValueError("recovery observation attempt/dispatch binding mismatch")
    if attempt.request_ref != request_ref or attempt.provider_id != provider_id:
        raise ValueError(
            "recovery observation attempt request/provider binding mismatch"
        )
    for key in (
        "invocation_permit_digest",
        "governance_requirement_digest",
        "governance_snapshot_digest",
    ):
        if metadata.get(key) != payload.get(key):
            raise ValueError(
                f"recovery observation dispatch {key} binding mismatch"
            )
    if attempt.lease_generation != payload.get("lease_generation"):
        raise ValueError("recovery observation lease generation binding mismatch")

    step = store.get_step(attempt.step_id)
    if step is None:
        raise ValueError("recovery observation requires durable Step")
    action_ref = metadata.get("action_ref")
    if not isinstance(action_ref, str) or not action_ref:
        raise ValueError(
            "recovery observation requires exact Attempt-to-Action binding"
        )
    action = store.get_action(action_ref)
    if action is None:
        raise ValueError("recovery observation requires durable Action")
    if action.request_ref != request_ref or action.provider_id != provider_id:
        raise ValueError(
            "recovery observation Action request/provider binding mismatch"
        )
    if action.run_id != step.run_id:
        raise ValueError("recovery observation Action/Step run binding mismatch")

    observation_identity = {
        "schema": RECOVERY_OBSERVATION_SCHEMA,
        "observation_instance_ref": instance_ref,
    }
    observation_id = f"recovery_observation_{_digest(observation_identity)[:32]}"
    event_payload = {
        "schema": RECOVERY_OBSERVATION_SCHEMA,
        "semantic_level": "recovery-observation",
        "authoritative_outcome": False,
        "observation_instance_ref": instance_ref,
        "dispatch_commit_ref": dispatch_ref,
        "action_ref": action.id,
        "attempt_ref": attempt.id,
        "step_ref": step.id,
        "request_ref": request_ref,
        "provider_id": provider_id,
        "idempotency_key": attempt.idempotency_key,
        "observation_source": source,
        "reported_status": request.reported_status,
        "provenance_refs": list(provenance),
    }
    event = Event(
        id=observation_id,
        type=RECOVERY_OBSERVATION_EVENT,
        subject_ref=dispatch_ref,
        payload=event_payload,
    )
    return PreparedRecoveryObservationCommit(
        observation=recovery_observation_from_event(event),
        event=event,
    )
