"""B4-P2 design audit: RecoveryObservation must not become a second Outcome authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.verified_outcome_commit import VerifiedOutcomeCommitRequest
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.recovery_observation import RecoveryObservationCommitRequest

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("patch:v2",)


@dataclass(frozen=True)
class _Graph:
    work: Work
    run: Run
    step: Step
    attempt: StepAttempt
    action: Action
    dispatch_ref: str


def _dispatch_ref(payload: dict[str, object]) -> str:
    identity = {
        "schema": payload["schema"],
        "request_id": payload["request_id"],
        "provider_id": payload["provider_id"],
        "attempt_id": payload["attempt_ref"],
        "invocation_permit_digest": payload["invocation_permit_digest"],
        "governance_requirement_digest": payload["governance_requirement_digest"],
        "governance_snapshot_digest": payload["governance_snapshot_digest"],
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return f"dispatch_{hashlib.sha256(raw.encode()).hexdigest()}"


def _seed_graph(store: InMemoryStateStore, suffix: str) -> _Graph:
    work = Work(id=f"work_p2_{suffix}", title="B4-P2 audit")
    run = Run(id=f"run_p2_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_p2_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    request_ref = f"request_p2_{suffix}"
    provider_id = f"provider:p2:{suffix}"
    action = Action(
        id=f"action_p2_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="deploy.apply",
        provider_id=provider_id,
        request_ref=request_ref,
        status="succeeded",
    )
    attempt = StepAttempt(
        id=f"attempt_p2_{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider_id,
        request_ref=request_ref,
        idempotency_key=f"idem:{suffix}",
        status="succeeded",
        lease_generation=0,
        metadata={"action_ref": action.id},
    )
    payload: dict[str, object] = {
        "schema": "governance-dispatch-commit-v1",
        "request_id": request_ref,
        "provider_id": provider_id,
        "attempt_ref": attempt.id,
        "invocation_permit_digest": f"permit:{suffix}",
        "qualification_digest": f"qualification:{suffix}",
        "governance_requirement_digest": f"requirement:{suffix}",
        "governance_snapshot_digest": f"snapshot:{suffix}",
        "lease_generation": 0,
        "linearization_domain": "authoritative-state-store",
    }
    dispatch_ref = _dispatch_ref(payload)
    attempt.metadata.update(
        {
            "dispatch_commit_ref": dispatch_ref,
            "invocation_permit_digest": payload["invocation_permit_digest"],
            "governance_requirement_digest": payload["governance_requirement_digest"],
            "governance_snapshot_digest": payload["governance_snapshot_digest"],
        }
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    store.append_event(
        Event(
            id=dispatch_ref,
            type="InvocationDispatchCommitted",
            subject_ref=request_ref,
            payload=payload,
        )
    )
    return _Graph(work, run, step, attempt, action, dispatch_ref)


def _observe(
    store: InMemoryStateStore,
    graph: _Graph,
    *,
    instance: str,
    reported_status: str,
):
    return store.commit_recovery_observation(
        RecoveryObservationCommitRequest(
            observation_instance_ref=instance,
            dispatch_commit_ref=graph.dispatch_ref,
            observation_source="provider-reconcile",
            reported_status=reported_status,  # type: ignore[arg-type]
            provenance_refs=(graph.attempt.provider_id,),
        )
    )


def _proof(
    store: InMemoryStateStore,
    graph: _Graph,
    *,
    suffix: str,
    result: str = "pass",
    extra_source_refs: tuple[str, ...] = (),
    metadata_updates: dict[str, Any] | None = None,
) -> EvidenceArtifact:
    metadata: dict[str, Any] = {
        "verification_result": {"result": result},
        "proof_class": "objective-verification",
        "action_ref": graph.action.id,
        "request_id": graph.action.request_ref,
        "attempt_ref": graph.attempt.id,
        "work_id": graph.work.id,
        "run_id": graph.run.id,
        "verification_scope": dict(_SCOPE),
        "subject_version_refs": list(_VERSIONS),
        "verifier_provenance": {
            "verifier_id": "verifier:p2-audit",
            "provider_id": "verifier:p2-audit",
            "method": "closed-verification",
        },
    }
    if metadata_updates:
        metadata.update(metadata_updates)
    proof = EvidenceArtifact(
        id=f"evidence_p2_{suffix}",
        kind="task-objective-proof",
        source_refs=[graph.action.id, *extra_source_refs],
        metadata=metadata,
    )
    store.save_record(proof)
    return proof


def _request(graph: _Graph, evidence_refs: tuple[str, ...]) -> VerifiedOutcomeCommitRequest:
    return VerifiedOutcomeCommitRequest(
        action_ref=graph.action.id,
        evidence_refs=evidence_refs,
        expected_work_id=graph.work.id,
        expected_run_id=graph.run.id,
        expected_request_id=graph.action.request_ref,
        expected_attempt_ref=graph.attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=_VERSIONS,
    )


def test_p2_audit_recovery_observation_is_not_typed_objective_evidence() -> None:
    store = InMemoryStateStore()
    graph = _seed_graph(store, "direct")
    observation = _observe(
        store,
        graph,
        instance="observation:p2:direct",
        reported_status="reported-succeeded",
    )

    with pytest.raises(ValueError, match="typed EvidenceArtifact"):
        store.commit_verified_outcome(_request(graph, (observation.id,)))

    assert store.list_records("Outcome") == []


def test_p2_audit_observation_citation_cannot_replace_existing_action_binding() -> None:
    store = InMemoryStateStore()
    graph = _seed_graph(store, "binding")
    observation = _observe(
        store,
        graph,
        instance="observation:p2:binding",
        reported_status="reported-succeeded",
    )
    proof = _proof(
        store,
        graph,
        suffix="missing-action-source",
        extra_source_refs=(observation.id,),
    )
    proof = proof.model_copy(update={"source_refs": [observation.id]})
    store.save_record(proof)

    with pytest.raises(ValueError, match="exact Action"):
        store.commit_verified_outcome(_request(graph, (proof.id,)))


def test_p2_audit_observation_citation_cannot_replace_scope_or_version_binding() -> None:
    store = InMemoryStateStore()
    graph = _seed_graph(store, "scope")
    observation = _observe(
        store,
        graph,
        instance="observation:p2:scope",
        reported_status="reported-succeeded",
    )
    proof = _proof(
        store,
        graph,
        suffix="wrong-version",
        extra_source_refs=(observation.id,),
        metadata_updates={"subject_version_refs": ["patch:v1"]},
    )

    with pytest.raises(ValueError, match="subject version"):
        store.commit_verified_outcome(_request(graph, (proof.id,)))


def test_p2_audit_cross_action_observation_ref_is_opaque_not_an_authority_edge() -> None:
    store = InMemoryStateStore()
    source_graph = _seed_graph(store, "source-action")
    target_graph = _seed_graph(store, "target-action")
    observation = _observe(
        store,
        source_graph,
        instance="observation:p2:cross-action",
        reported_status="reported-succeeded",
    )
    proof = _proof(
        store,
        target_graph,
        suffix="cross-action-proof",
        extra_source_refs=(observation.id,),
        metadata_updates={"recovery_observation_refs": [observation.id]},
    )

    outcome = store.commit_verified_outcome(_request(target_graph, (proof.id,)))

    assert outcome.action_ref == target_graph.action.id
    assert outcome.evidence_refs == [proof.id]
    assert observation.id not in outcome.evidence_refs
    authority_events = [
        event
        for event in store.list_events()
        if event.type in {"ObjectiveVerificationAccepted", "OutcomeConfirmed"}
        and event.subject_ref == outcome.id
    ]
    assert authority_events
    assert all(event.payload["verification_refs"] == [proof.id] for event in authority_events)


def test_p2_audit_stale_observation_cannot_substitute_for_new_attempt_binding() -> None:
    store = InMemoryStateStore()
    stale_graph = _seed_graph(store, "stale-attempt")
    current_graph = _seed_graph(store, "current-attempt")
    observation = _observe(
        store,
        stale_graph,
        instance="observation:p2:stale",
        reported_status="reported-succeeded",
    )
    proof = _proof(
        store,
        current_graph,
        suffix="stale-attempt-proof",
        extra_source_refs=(observation.id,),
        metadata_updates={
            "attempt_ref": stale_graph.attempt.id,
            "recovery_observation_refs": [observation.id],
        },
    )

    with pytest.raises(ValueError, match="attempt binding"):
        store.commit_verified_outcome(_request(current_graph, (proof.id,)))


def test_p2_audit_conflicting_observations_do_not_implement_latest_wins() -> None:
    store = InMemoryStateStore()
    graph = _seed_graph(store, "conflict")
    first = _observe(
        store,
        graph,
        instance="observation:p2:conflict:1",
        reported_status="reported-succeeded",
    )
    latest = _observe(
        store,
        graph,
        instance="observation:p2:conflict:2",
        reported_status="reported-failed",
    )
    proof = _proof(
        store,
        graph,
        suffix="conflict-proof",
        result="pass",
        extra_source_refs=(first.id, latest.id),
        metadata_updates={"recovery_observation_refs": [first.id, latest.id]},
    )

    outcome = store.commit_verified_outcome(_request(graph, (proof.id,)))

    assert latest.reported_status == "reported-failed"
    assert outcome.metadata["objective_result"] == "pass"
    assert outcome.evidence_refs == [proof.id]


def test_p2_audit_reported_status_cannot_masquerade_as_closed_verification_result() -> None:
    store = InMemoryStateStore()
    graph = _seed_graph(store, "reported-result")
    observation = _observe(
        store,
        graph,
        instance="observation:p2:reported-result",
        reported_status="reported-succeeded",
    )
    proof = _proof(
        store,
        graph,
        suffix="reported-result-proof",
        result="reported-succeeded",
        extra_source_refs=(observation.id,),
    )

    with pytest.raises(ValueError, match="explicit pass or fail"):
        store.commit_verified_outcome(_request(graph, (proof.id,)))
