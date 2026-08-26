from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.records.verified_outcome_commit import VerifiedOutcomeCommitRequest
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("patch:v1",)


@contextmanager
def _store(backend: str, tmp_path: Path) -> Iterator[InMemoryStateStore | SQLiteStateStore]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"verified-outcome-{backend}.db")
    try:
        yield store
    finally:
        store.close()


def _seed(store: Any) -> tuple[Work, Run, Step, StepAttempt, Action]:
    work = Work(id="work_voc", title="verified outcome")
    run = Run(id="run_voc", work_id=work.id, status="running")
    step = Step(id="step_voc", run_id=run.id, step_key="effect", status="succeeded")
    attempt = StepAttempt(
        id="attempt_voc",
        step_id=step.id,
        provider_id="executor",
        request_ref="request_voc",
        status="succeeded",
    )
    action = Action(
        id="action_voc",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref="request_voc",
        status="succeeded",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    return work, run, step, attempt, action


def _proof(
    store: Any,
    *,
    work: Work,
    run: Run,
    attempt: StepAttempt,
    action: Action,
    result: str,
    suffix: str,
) -> EvidenceArtifact:
    proof = EvidenceArtifact(
        id=f"evidence_voc_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        metadata={
            "verification_result": {"result": result},
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
                "provider_id": "verifier",
                "verifier_id": "verifier:objective",
                "method": "closed-verification",
            },
        },
    )
    store.save_record(proof)
    return proof


def _request(action: Action, work: Work, run: Run, attempt: StepAttempt, refs: list[str]) -> VerifiedOutcomeCommitRequest:
    return VerifiedOutcomeCommitRequest(
        action_ref=action.id,
        evidence_refs=tuple(refs),
        expected_work_id=work.id,
        expected_run_id=run.id,
        expected_request_id=action.request_ref,
        expected_attempt_ref=attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=_VERSIONS,
    )


def _authority_events(store: Any) -> list[Any]:
    return [
        event
        for event in store.list_events()
        if event.type in {"ObjectiveVerificationAccepted", "OutcomeConfirmed"}
    ]


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("result", ["pass", "fail"])
def test_fb2_p4_commit_derives_confirmed_outcome_from_bound_proof(
    backend: str,
    result: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as store:
        work, run, _step, attempt, action = _seed(store)
        proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result=result, suffix=result)
        outcome = store.commit_verified_outcome(_request(action, work, run, attempt, [proof.id]))
        assert isinstance(outcome, OutcomeRecord)
        assert outcome.lifecycle_status == "confirmed"
        assert outcome.metadata["objective_result"] == result
        assert outcome.action_ref == action.id
        assert outcome.evidence_refs == [proof.id]
        events = sorted(_authority_events(store), key=lambda item: item.type)
        assert [event.type for event in events] == ["ObjectiveVerificationAccepted", "OutcomeConfirmed"]
        assert all(event.payload["outcome_ref"] == outcome.id for event in events)
        assert all(event.payload["authoritative_outcome"] is True for event in events)
        assert all(event.payload["semantic_level"] == "objective-verification" for event in events)
        assert all(event.payload["objective_result"] == result for event in events)
        assert all(
            event.payload["verification_binding_digest"] == outcome.metadata["verification_binding_digest"]
            for event in events
        )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb2_p4_same_closure_replay_is_idempotent_and_order_stable(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as store:
        work, run, _step, attempt, action = _seed(store)
        proof_a = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass", suffix="a")
        proof_b = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass", suffix="b")
        first = store.commit_verified_outcome(_request(action, work, run, attempt, [proof_a.id, proof_b.id]))
        second = store.commit_verified_outcome(_request(action, work, run, attempt, [proof_b.id, proof_a.id]))
        assert second.id == first.id
        assert len([r for r in store.list_records("Outcome") if r.lifecycle_status == "confirmed"]) == 1
        assert len(_authority_events(store)) == 2


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb2_p4_mixed_objective_results_fail_closed(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as store:
        work, run, _step, attempt, action = _seed(store)
        passed = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass", suffix="pass")
        failed = _proof(store, work=work, run=run, attempt=attempt, action=action, result="fail", suffix="fail")
        with pytest.raises(ValueError, match="inconsistent verification closure"):
            store.commit_verified_outcome(_request(action, work, run, attempt, [passed.id, failed.id]))
        assert [r for r in store.list_records("Outcome") if r.lifecycle_status == "confirmed"] == []
        assert _authority_events(store) == []


def test_fb2_p4_commit_rechecks_durable_execution_graph() -> None:
    store = InMemoryStateStore()
    work, run, _step, attempt, action = _seed(store)
    proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass", suffix="graph")
    store.save_action(action.model_copy(update={"provider_id": "changed-executor"}))
    with pytest.raises(ValueError, match="provider identity"):
        store.commit_verified_outcome(_request(action, work, run, attempt, [proof.id]))
    assert [r for r in store.list_records("Outcome") if r.lifecycle_status == "confirmed"] == []


def test_fb2_p4_authority_event_failure_rolls_back_outcome_and_prefix_event() -> None:
    class FailingEventStore(InMemoryStateStore):
        def append_event(self, value: Any) -> None:
            if getattr(value, "type", "") == "OutcomeConfirmed":
                raise RuntimeError("simulated authority journal failure")
            super().append_event(value)

    store = FailingEventStore()
    work, run, _step, attempt, action = _seed(store)
    proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass", suffix="rollback")
    with pytest.raises(RuntimeError, match="authority journal failure"):
        store.commit_verified_outcome(_request(action, work, run, attempt, [proof.id]))
    assert [r for r in store.list_records("Outcome") if r.lifecycle_status == "confirmed"] == []
    assert _authority_events(store) == []
