"""Pure authoritative preparation for durable recovery dispositions.

This module owns basis reconstruction and deterministic decision preparation.
It does not persist decisions or consume them to perform follow-on work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.governance.dispatch import (
    DISPATCH_COMMIT_EVENT,
    DISPATCH_COMMIT_SCHEMA,
    DispatchRecoveryMode,
    dispatch_recovery_mode,
)
from portable_runtime.records.models import OutcomeRecord
from portable_runtime.records.verified_outcome_commit import (
    VerifiedOutcomeCommitRequest,
    prepare_verified_outcome_commit,
    same_verified_outcome_semantics,
)
from portable_runtime.workflows.recovery_observation import (
    RECOVERY_OBSERVATION_EVENT,
    RecoveryObservation,
    recovery_observation_from_event,
)

RECOVERY_DISPOSITION_EVENT = "RecoveryDispositionRecorded"
RECOVERY_DISPOSITION_SCHEMA = "recovery-disposition-v1"

RecoveryDispositionAction = Literal[
    "hold-unresolved",
    "reconcile-again",
    "retry-idempotent",
    "require-manual-resolution",
    "accept-objective-resolution",
]
_ALLOWED_ACTIONS = frozenset(
    {
        "hold-unresolved",
        "reconcile-again",
        "retry-idempotent",
        "require-manual-resolution",
        "accept-objective-resolution",
    }
)


@dataclass(frozen=True)
class RecoveryDispositionCommitRequest:
    """Exact caller-selected fact refs plus one policy identity."""

    dispatch_commit_ref: str
    observation_refs: tuple[str, ...]
    outcome_refs: tuple[str, ...]
    policy_ref: str


@dataclass(frozen=True)
class RecoveryDispositionBasis:
    """Authoritatively reconstructed, canonical decision basis."""

    basis_key: str
    dispatch_commit_ref: str
    observation_refs: tuple[str, ...]
    outcome_refs: tuple[str, ...]
    recovery_mode: DispatchRecoveryMode
    effect_semantics: str
    reversibility: str
    policy_ref: str
    action_ref: str
    attempt_ref: str
    step_ref: str
    request_ref: str
    provider_id: str
    run_ref: str
    work_ref: str


@dataclass(frozen=True)
class RecoveryDisposition:
    """One prepared recovery decision for one exact basis identity."""

    id: str
    basis_key: str
    dispatch_commit_ref: str
    observation_refs: tuple[str, ...]
    outcome_refs: tuple[str, ...]
    recovery_mode: DispatchRecoveryMode
    effect_semantics: str
    reversibility: str
    policy_ref: str
    action: RecoveryDispositionAction


@dataclass(frozen=True)
class PreparedRecoveryDisposition:
    basis: RecoveryDispositionBasis
    disposition: RecoveryDisposition
    event: Event


class RecoveryDispositionStoreReader(Protocol):
    def get_event(self, event_id: str) -> Event | None: ...
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: ...
    def get_step(self, step_id: str) -> Step | None: ...
    def get_action(self, action_id: str) -> Action | None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def get_work(self, work_id: str) -> Work | None: ...
    def get_record(self, record_id: str) -> object | None: ...


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"recovery disposition requires {label}")
    return value.strip()


def _canonical_refs(refs: tuple[str, ...], label: str, *, required: bool) -> tuple[str, ...]:
    values: list[str] = []
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f"recovery disposition {label} refs must be non-empty strings")
        values.append(ref.strip())
    canonical = tuple(sorted(set(values)))
    if required and not canonical:
        raise ValueError(f"recovery disposition requires {label} refs")
    return canonical


def _dispatch_identity(payload: dict[str, Any]) -> str:
    identity = {
        "schema": payload.get("schema"),
        "request_id": payload.get("request_id"),
        "provider_id": payload.get("provider_id"),
        "attempt_id": payload.get("attempt_ref"),
        "invocation_permit_digest": payload.get("invocation_permit_digest"),
        "governance_requirement_digest": payload.get("governance_requirement_digest"),
        "governance_snapshot_digest": payload.get("governance_snapshot_digest"),
    }
    return f"dispatch_{_digest(identity)}"


def _basis_identity(
    *,
    dispatch_commit_ref: str,
    observation_refs: tuple[str, ...],
    outcome_refs: tuple[str, ...],
    recovery_mode: DispatchRecoveryMode,
    effect_semantics: str,
    reversibility: str,
    policy_ref: str,
) -> str:
    return _digest(
        {
            "schema": RECOVERY_DISPOSITION_SCHEMA,
            "dispatch_commit_ref": dispatch_commit_ref,
            "observation_refs": list(observation_refs),
            "outcome_refs": list(outcome_refs),
            "recovery_mode": recovery_mode,
            "effect_semantics": effect_semantics,
            "reversibility": reversibility,
            "policy_ref": policy_ref,
        }
    )


def _reconstruct_dispatch_graph(
    store: RecoveryDispositionStoreReader,
    dispatch_ref: str,
) -> tuple[Event, StepAttempt, Step, Action, Run, Work]:
    dispatch = store.get_event(dispatch_ref)
    if dispatch is None or dispatch.type != DISPATCH_COMMIT_EVENT:
        raise ValueError("recovery disposition requires exact InvocationDispatchCommitted event")
    payload = dispatch.payload if isinstance(dispatch.payload, dict) else {}
    if payload.get("schema") != DISPATCH_COMMIT_SCHEMA:
        raise ValueError("recovery disposition dispatch schema mismatch")
    if payload.get("linearization_domain") != "authoritative-state-store":
        raise ValueError("recovery disposition dispatch linearization domain mismatch")
    if _dispatch_identity(payload) != dispatch.id or dispatch.id != dispatch_ref:
        raise ValueError("recovery disposition dispatch deterministic identity mismatch")

    request_ref = _required_string(payload.get("request_id"), "dispatch request_ref")
    provider_id = _required_string(payload.get("provider_id"), "dispatch provider_id")
    attempt_ref = _required_string(payload.get("attempt_ref"), "dispatch attempt_ref")
    if dispatch.subject_ref != request_ref:
        raise ValueError("recovery disposition dispatch subject binding mismatch")

    attempt = store.get_attempt(attempt_ref)
    if attempt is None:
        raise ValueError("recovery disposition requires durable StepAttempt")
    metadata = attempt.metadata if isinstance(attempt.metadata, dict) else {}
    if metadata.get("dispatch_commit_ref") != dispatch_ref:
        raise ValueError("recovery disposition attempt/dispatch binding mismatch")
    if attempt.request_ref != request_ref or attempt.provider_id != provider_id:
        raise ValueError("recovery disposition attempt request/provider binding mismatch")
    for key in (
        "invocation_permit_digest",
        "governance_requirement_digest",
        "governance_snapshot_digest",
    ):
        if metadata.get(key) != payload.get(key):
            raise ValueError(f"recovery disposition dispatch {key} binding mismatch")
    if attempt.lease_generation != payload.get("lease_generation"):
        raise ValueError("recovery disposition lease generation binding mismatch")

    step = store.get_step(attempt.step_id)
    if step is None:
        raise ValueError("recovery disposition requires durable Step")
    action_ref = _required_string(metadata.get("action_ref"), "Attempt-to-Action binding")
    action = store.get_action(action_ref)
    if action is None:
        raise ValueError("recovery disposition requires durable Action")
    if action.request_ref != request_ref or action.provider_id != provider_id:
        raise ValueError("recovery disposition Action request/provider binding mismatch")
    if action.run_id != step.run_id:
        raise ValueError("recovery disposition Action/Step run binding mismatch")

    run = store.get_run(step.run_id)
    if run is None or run.id != action.run_id:
        raise ValueError("recovery disposition requires exact Run binding")
    work = store.get_work(run.work_id)
    if work is None or action.work_id != work.id:
        raise ValueError("recovery disposition requires exact Work binding")
    return dispatch, attempt, step, action, run, work


def _validate_observation(
    store: RecoveryDispositionStoreReader,
    ref: str,
    *,
    dispatch_ref: str,
    attempt: StepAttempt,
    step: Step,
    action: Action,
) -> RecoveryObservation:
    event = store.get_event(ref)
    if event is None or event.id != ref or event.type != RECOVERY_OBSERVATION_EVENT:
        raise ValueError("recovery disposition requires exact RecoveryObservation fact")
    if event.subject_ref != dispatch_ref:
        raise ValueError("RecoveryObservation is not bound to recovery dispatch")
    observation = recovery_observation_from_event(event)
    expected = {
        "dispatch_commit_ref": dispatch_ref,
        "action_ref": action.id,
        "attempt_ref": attempt.id,
        "step_ref": step.id,
        "request_ref": action.request_ref,
        "provider_id": action.provider_id,
    }
    for field, value in expected.items():
        if getattr(observation, field) != value:
            raise ValueError(f"RecoveryObservation {field} binding mismatch")
    return observation


def _validate_confirmed_outcome(
    store: RecoveryDispositionStoreReader,
    ref: str,
    *,
    attempt: StepAttempt,
    action: Action,
    run: Run,
    work: Work,
) -> OutcomeRecord:
    persisted = store.get_record(ref)
    if not isinstance(persisted, OutcomeRecord) or persisted.id != ref:
        raise ValueError("recovery disposition requires exact Outcome record")
    if persisted.lifecycle_status != "confirmed":
        raise ValueError("recovery disposition Outcome must be confirmed")
    if persisted.action_ref != action.id:
        raise ValueError("recovery disposition Outcome must bind exact recovery Action")

    metadata = persisted.metadata if isinstance(persisted.metadata, dict) else {}
    expected_metadata = {
        "work_id": work.id,
        "run_id": run.id,
        "request_id": action.request_ref,
        "attempt_ref": attempt.id,
    }
    for key, value in expected_metadata.items():
        if metadata.get(key) != value:
            raise ValueError(f"recovery disposition Outcome {key} binding mismatch")
    scope = metadata.get("verification_scope")
    versions = metadata.get("subject_version_refs")
    if not isinstance(scope, dict):
        raise ValueError("recovery disposition Outcome verification scope is missing")
    if not isinstance(versions, list) or not all(
        isinstance(value, str) and value for value in versions
    ):
        raise ValueError("recovery disposition Outcome subject versions are invalid")

    prepared = prepare_verified_outcome_commit(
        store,
        VerifiedOutcomeCommitRequest(
            action_ref=action.id,
            evidence_refs=tuple(persisted.evidence_refs),
            expected_work_id=work.id,
            expected_run_id=run.id,
            expected_request_id=action.request_ref,
            expected_attempt_ref=attempt.id,
            verification_scope={str(key): value for key, value in scope.items()},
            subject_version_refs=tuple(versions),
        ),
    )
    if not same_verified_outcome_semantics(persisted, prepared.outcome):
        raise ValueError("recovery disposition Outcome authority semantics mismatch")
    if prepared.outcome.id != ref:
        raise ValueError("recovery disposition Outcome deterministic identity mismatch")
    for authority_event in prepared.events:
        event = store.get_event(authority_event.id)
        if event is None or not same_verified_outcome_semantics(event, authority_event):
            raise ValueError("recovery disposition Outcome authority event graph incomplete")
    return persisted


def reconstruct_recovery_disposition_basis(
    store: RecoveryDispositionStoreReader,
    request: RecoveryDispositionCommitRequest,
) -> RecoveryDispositionBasis:
    """Re-read exact authoritative facts and derive one canonical recovery basis."""

    dispatch_ref = _required_string(request.dispatch_commit_ref, "dispatch_commit_ref")
    policy_ref = _required_string(request.policy_ref, "policy_ref")
    observation_refs = _canonical_refs(
        request.observation_refs,
        "observation",
        required=True,
    )
    outcome_refs = _canonical_refs(request.outcome_refs, "outcome", required=False)

    _, attempt, step, action, run, work = _reconstruct_dispatch_graph(store, dispatch_ref)
    for ref in observation_refs:
        _validate_observation(
            store,
            ref,
            dispatch_ref=dispatch_ref,
            attempt=attempt,
            step=step,
            action=action,
        )
    for ref in outcome_refs:
        _validate_confirmed_outcome(
            store,
            ref,
            attempt=attempt,
            action=action,
            run=run,
            work=work,
        )

    recovery_mode = dispatch_recovery_mode(step, attempt)
    if recovery_mode == "uncommitted":
        raise ValueError("recovery disposition cannot use an uncommitted dispatch")
    effect_semantics = _required_string(step.effect_semantics, "effect semantics")
    reversibility = _required_string(step.reversibility, "reversibility")
    basis_key = _basis_identity(
        dispatch_commit_ref=dispatch_ref,
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        recovery_mode=recovery_mode,
        effect_semantics=effect_semantics,
        reversibility=reversibility,
        policy_ref=policy_ref,
    )
    return RecoveryDispositionBasis(
        basis_key=basis_key,
        dispatch_commit_ref=dispatch_ref,
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        recovery_mode=recovery_mode,
        effect_semantics=effect_semantics,
        reversibility=reversibility,
        policy_ref=policy_ref,
        action_ref=action.id,
        attempt_ref=attempt.id,
        step_ref=step.id,
        request_ref=action.request_ref,
        provider_id=action.provider_id,
        run_ref=run.id,
        work_ref=work.id,
    )


def _policy_action(policy: Any, basis: RecoveryDispositionBasis) -> RecoveryDispositionAction:
    decider = getattr(policy, "decide", None)
    if callable(decider):
        value = decider(basis)
    elif callable(policy):
        value = policy(basis)
    else:
        raise ValueError("recovery disposition policy must be callable")
    if not isinstance(value, str) or value not in _ALLOWED_ACTIONS:
        raise ValueError("recovery disposition policy returned unsupported action")
    return cast(RecoveryDispositionAction, value)


def prepare_recovery_disposition(
    basis: RecoveryDispositionBasis,
    policy: Any,
) -> PreparedRecoveryDisposition:
    """Evaluate policy once and prepare deterministic decision semantics."""

    action = _policy_action(policy, basis)
    disposition_id = f"recovery_disposition_{basis.basis_key[:32]}"
    disposition = RecoveryDisposition(
        id=disposition_id,
        basis_key=basis.basis_key,
        dispatch_commit_ref=basis.dispatch_commit_ref,
        observation_refs=basis.observation_refs,
        outcome_refs=basis.outcome_refs,
        recovery_mode=basis.recovery_mode,
        effect_semantics=basis.effect_semantics,
        reversibility=basis.reversibility,
        policy_ref=basis.policy_ref,
        action=action,
    )
    event = Event(
        id=disposition.id,
        type=RECOVERY_DISPOSITION_EVENT,
        subject_ref=basis.dispatch_commit_ref,
        payload={
            "schema": RECOVERY_DISPOSITION_SCHEMA,
            "semantic_level": "recovery-disposition",
            "basis_key": basis.basis_key,
            "dispatch_commit_ref": basis.dispatch_commit_ref,
            "observation_refs": list(basis.observation_refs),
            "outcome_refs": list(basis.outcome_refs),
            "recovery_mode": basis.recovery_mode,
            "effect_semantics": basis.effect_semantics,
            "reversibility": basis.reversibility,
            "policy_ref": basis.policy_ref,
            "action": action,
        },
    )
    return PreparedRecoveryDisposition(basis=basis, disposition=disposition, event=event)


def recovery_disposition_from_event(event: Event) -> RecoveryDisposition:
    """Decode and verify one durable disposition event."""

    if event.type != RECOVERY_DISPOSITION_EVENT:
        raise ValueError("event is not a RecoveryDispositionRecorded fact")
    payload = event.payload if isinstance(event.payload, dict) else {}
    if payload.get("schema") != RECOVERY_DISPOSITION_SCHEMA:
        raise ValueError("unsupported recovery disposition schema")
    if payload.get("semantic_level") != "recovery-disposition":
        raise ValueError("recovery disposition semantic level mismatch")
    dispatch_ref = _required_string(payload.get("dispatch_commit_ref"), "dispatch_commit_ref")
    policy_ref = _required_string(payload.get("policy_ref"), "policy_ref")
    raw_observations = payload.get("observation_refs")
    raw_outcomes = payload.get("outcome_refs")
    if not isinstance(raw_observations, list) or not all(isinstance(v, str) for v in raw_observations):
        raise ValueError("invalid recovery disposition observation refs")
    if not isinstance(raw_outcomes, list) or not all(isinstance(v, str) for v in raw_outcomes):
        raise ValueError("invalid recovery disposition outcome refs")
    observation_refs = _canonical_refs(tuple(raw_observations), "observation", required=True)
    outcome_refs = _canonical_refs(tuple(raw_outcomes), "outcome", required=False)
    if list(observation_refs) != raw_observations or list(outcome_refs) != raw_outcomes:
        raise ValueError("recovery disposition refs are not canonical")

    recovery_mode = payload.get("recovery_mode")
    if recovery_mode not in {"idempotent-retry", "reconcile", "unknown"}:
        raise ValueError("invalid recovery disposition recovery mode")
    effect_semantics = _required_string(payload.get("effect_semantics"), "effect semantics")
    reversibility = _required_string(payload.get("reversibility"), "reversibility")
    action = payload.get("action")
    if action not in _ALLOWED_ACTIONS:
        raise ValueError("invalid recovery disposition action")
    basis_key = _basis_identity(
        dispatch_commit_ref=dispatch_ref,
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        recovery_mode=cast(DispatchRecoveryMode, recovery_mode),
        effect_semantics=effect_semantics,
        reversibility=reversibility,
        policy_ref=policy_ref,
    )
    if payload.get("basis_key") != basis_key:
        raise ValueError("recovery disposition basis identity mismatch")
    expected_id = f"recovery_disposition_{basis_key[:32]}"
    if event.id != expected_id or event.subject_ref != dispatch_ref:
        raise ValueError("recovery disposition deterministic identity mismatch")
    return RecoveryDisposition(
        id=event.id,
        basis_key=basis_key,
        dispatch_commit_ref=dispatch_ref,
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        recovery_mode=cast(DispatchRecoveryMode, recovery_mode),
        effect_semantics=effect_semantics,
        reversibility=reversibility,
        policy_ref=policy_ref,
        action=cast(RecoveryDispositionAction, action),
    )
