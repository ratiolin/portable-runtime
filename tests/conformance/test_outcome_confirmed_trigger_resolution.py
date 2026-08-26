"""F1-B3 P1a: only the complete F1-B2 authority graph may trigger governance impact."""

from __future__ import annotations

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.governance.outcome_impact import resolve_outcome_confirmed_trigger
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ["subject:v1"]


def _confirmed(store: InMemoryStateStore, suffix: str = "valid"):
    work = Work(id=f"work_b3_trigger_{suffix}", title="trigger", metadata={"work_version": 1})
    run = Run(id=f"run_b3_trigger_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_b3_trigger_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_b3_trigger_{suffix}",
        step_id=step.id,
        provider_id="provider:executor",
        request_ref=f"request_b3_trigger_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_b3_trigger_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id=attempt.provider_id,
        request_ref=attempt.request_ref or "",
        status="succeeded",
    )
    for saver, value in (
        (store.save_work, work),
        (store.save_run, run),
        (store.save_step, step),
        (store.save_attempt, attempt),
        (store.save_action, action),
    ):
        saver(value)
    proof = EvidenceArtifact(
        id=f"evidence_b3_trigger_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        lifecycle_status="current",
        metadata={
            "verification_result": {"result": "pass"},
            "proof_class": "objective-verification",
            "action_ref": action.id,
            "request_id": action.request_ref,
            "attempt_ref": attempt.id,
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": dict(_SCOPE),
            "subject_version_refs": list(_VERSIONS),
            "obligation_refs": ["verify.effect"],
            "verifier_provenance": {
                "provider_id": "provider:verifier",
                "verifier_id": "verifier:objective",
                "method": "closed-verification",
            },
        },
    )
    store.save_record(proof)
    outcome = VerifiedOutcomeAuthority(store).confirm(
        action_ref=action.id,
        evidence_refs=[proof.id],
        expected_work_id=work.id,
        expected_run_id=run.id,
        expected_request_id=action.request_ref,
        expected_attempt_ref=attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=list(_VERSIONS),
    )
    confirmed_event = next(
        event for event in store.list_events(outcome.id) if event.type == "OutcomeConfirmed"
    )
    return outcome, confirmed_event


def test_b3_p1a_valid_f1_b2_authority_graph_resolves_trigger() -> None:
    store = InMemoryStateStore()
    outcome, event = _confirmed(store)
    resolved = resolve_outcome_confirmed_trigger(store, event.id)
    assert resolved.status == "ready"
    assert resolved.authoritative
    assert resolved.outcome is not None and resolved.outcome.id == outcome.id
    assert resolved.accepted_event is not None
    assert resolved.accepted_event.type == "ObjectiveVerificationAccepted"
    assert resolved.prepared is not None
    assert resolved.prepared.events[1].id == event.id


def test_b3_a01_forged_outcome_confirmed_event_is_not_a_governance_trigger() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    forged = Event(
        id="event_outcome_confirmed_forged",
        type="OutcomeConfirmed",
        subject_ref="outcome_missing",
        payload={
            "semantic_level": "objective-verification",
            "authoritative_outcome": True,
            "objective_result": "pass",
            "outcome_ref": "outcome_missing",
            "verification_binding_digest": "forged",
        },
    )
    store.append_event(forged)

    resolved = resolve_outcome_confirmed_trigger(store, forged.id)

    assert resolved.status == "unavailable"
    assert not resolved.authoritative
    assert persistence.processed_event_obligation_ids(forged.id) is None
    assert persistence.list_obligations() == {}


def test_b3_p1a_matching_looking_forged_event_cannot_reuse_valid_outcome() -> None:
    store = InMemoryStateStore()
    outcome, valid = _confirmed(store, "forged-payload")
    forged = Event(
        id="event_outcome_confirmed_forged_payload",
        type="OutcomeConfirmed",
        subject_ref=outcome.id,
        payload={**valid.payload, "verification_binding_digest": "digest:forged"},
    )
    store.append_event(forged)
    resolved = resolve_outcome_confirmed_trigger(store, forged.id)
    assert resolved.status == "unavailable"
    assert resolved.reason == "authority-graph-mismatch"
