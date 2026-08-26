from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.records.verified_outcome_commit import VerifiedOutcomeCommitRequest
from portable_runtime.records.verified_outcome_replay import (
    VerifiedOutcomeAuthorityHistoryError,
    validate_verified_outcome_authority_graph,
)
from portable_runtime.stores.memory import InMemoryStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("patch:v1",)


def _candidate() -> tuple[dict[str, list[dict[str, object]]], OutcomeRecord]:
    store = InMemoryStateStore()
    work = Work(id="work_import_replay", title="verified outcome import replay")
    run = Run(id="run_import_replay", work_id=work.id, status="running")
    step = Step(id="step_import_replay", run_id=run.id, step_key="effect", status="succeeded")
    attempt = StepAttempt(
        id="attempt_import_replay",
        step_id=step.id,
        provider_id="executor",
        request_ref="request_import_replay",
        status="succeeded",
    )
    action = Action(
        id="action_import_replay",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref=attempt.request_ref,
        status="succeeded",
    )
    proof = EvidenceArtifact(
        id="evidence_import_replay",
        kind="task-objective-proof",
        source_refs=[action.id],
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
            "verifier_provenance": {
                "provider_id": "verifier",
                "verifier_id": "verifier:objective",
                "method": "closed-verification",
            },
        },
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    store.save_record(proof)
    outcome = store.commit_verified_outcome(
        VerifiedOutcomeCommitRequest(
            action_ref=action.id,
            evidence_refs=(proof.id,),
            expected_work_id=work.id,
            expected_run_id=run.id,
            expected_request_id=action.request_ref,
            expected_attempt_ref=attempt.id,
            verification_scope=dict(_SCOPE),
            subject_version_refs=_VERSIONS,
        )
    )
    return store.export_state(), outcome


def _find(state: dict[str, list[dict[str, object]]], kind: str, identifier: str) -> dict[str, object]:
    return next(value for value in state[kind] if value.get("id") == identifier)


def test_p5_1_candidate_replay_accepts_p4_authority_graph() -> None:
    state, outcome = _candidate()
    prepared = validate_verified_outcome_authority_graph(state)
    assert len(prepared) == 1
    assert prepared[0].outcome.id == outcome.id
    assert prepared[0].binding_digest == outcome.metadata["verification_binding_digest"]


@pytest.mark.parametrize("corruption", ["binding-digest", "execution-graph"])
def test_p5_1_candidate_replay_rejects_matching_looking_forgery(corruption: str) -> None:
    state, outcome = _candidate()
    forged = deepcopy(state)
    if corruption == "binding-digest":
        raw_outcome = _find(forged, "record", outcome.id)
        metadata = dict(raw_outcome["metadata"])  # type: ignore[arg-type]
        metadata["verification_binding_digest"] = "forged"
        raw_outcome["metadata"] = metadata
    else:
        raw_action = _find(forged, "action", outcome.action_ref)
        raw_action["provider_id"] = "different-executor"

    with pytest.raises(VerifiedOutcomeAuthorityHistoryError, match="incompatible confirmed-outcome authority history"):
        validate_verified_outcome_authority_graph(forged)


def test_p5_1_candidate_replay_requires_both_exact_authority_events() -> None:
    state, outcome = _candidate()
    forged = deepcopy(state)
    forged["event"] = [
        event
        for event in forged["event"]
        if not (event.get("type") == "OutcomeConfirmed" and event.get("subject_ref") == outcome.id)
    ]
    with pytest.raises(VerifiedOutcomeAuthorityHistoryError, match="required authority event missing"):
        validate_verified_outcome_authority_graph(forged)


def test_p5_1_candidate_replay_rejects_orphan_authority_event_under_wrong_id() -> None:
    state, _outcome = _candidate()
    forged = deepcopy(state)
    event = deepcopy(next(value for value in forged["event"] if value.get("type") == "OutcomeConfirmed"))
    event["id"] = "event_outcome_confirmed_forged_duplicate"
    forged["event"].append(event)
    with pytest.raises(VerifiedOutcomeAuthorityHistoryError, match="orphan or non-deterministic authority event"):
        validate_verified_outcome_authority_graph(forged)


def test_p5_1_recorded_outcome_has_no_objective_authority_requirement() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_recorded_only", title="recorded outcome")
    run = Run(id="run_recorded_only", work_id=work.id, status="running")
    action = Action(
        id="action_recorded_only",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref="request_recorded_only",
        status="succeeded",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_action(action)
    store.save_record(
        OutcomeRecord(
            id="outcome_recorded_only",
            action_ref=action.id,
            lifecycle_status="recorded",
            metadata={"note": "non-authoritative observation"},
        )
    )
    assert validate_verified_outcome_authority_graph(store.export_state()) == ()


def test_p5_1_authority_event_pointing_at_recorded_outcome_is_orphan() -> None:
    state, outcome = _candidate()
    forged: dict[str, list[dict[str, Any]]] = deepcopy(state)  # type: ignore[assignment]
    raw_outcome = _find(forged, "record", outcome.id)
    raw_outcome["lifecycle_status"] = "recorded"
    with pytest.raises(VerifiedOutcomeAuthorityHistoryError, match="orphan or non-deterministic authority event"):
        validate_verified_outcome_authority_graph(forged)
