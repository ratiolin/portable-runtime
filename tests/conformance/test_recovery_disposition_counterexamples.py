"""B4-P3 implementation counterexamples for durable RecoveryDisposition.

This file freezes semantics before any RecoveryDisposition production code exists.
The future request carries only exact fact refs plus policy/profile identity; the
store must re-read execution/recovery facts and derive classification itself.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservationCommitRequest,
)

_SCOPE = {"resource": "repo/recovery", "operation": "effect"}
_VERSIONS = ("subject:recovery:v1",)


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"recovery-disposition-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


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


def _seed_subject(store: Any, suffix: str) -> dict[str, Any]:
    work = Work(
        id=f"work_p3_{suffix}",
        title="RecoveryDisposition counterexample",
        metadata={"verification_scope": dict(_SCOPE), "work_version": 1},
    )
    run = Run(id=f"run_p3_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_p3_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="unknown",
        current_attempt=1,
        effect_semantics="reconcilable",
        side_effect_class="reconcilable",
    )
    request_ref = f"request_p3_{suffix}"
    provider_id = "provider:reconcile"
    action = Action(
        id=f"action_p3_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="deploy.apply",
        provider_id=provider_id,
        request_ref=request_ref,
        status="unknown",
    )
    attempt = StepAttempt(
        id=f"attempt_p3_{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider_id,
        request_ref=request_ref,
        idempotency_key=f"idempotency:{suffix}",
        status="unknown",
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
    return {
        "work": work,
        "run": run,
        "step": step,
        "attempt": attempt,
        "action": action,
        "dispatch_ref": dispatch_ref,
    }


def _observe(
    store: Any,
    graph: dict[str, Any],
    *,
    instance_ref: str,
    status: str = "reported-unknown",
) -> Any:
    return store.commit_recovery_observation(
        RecoveryObservationCommitRequest(
            observation_instance_ref=instance_ref,
            dispatch_commit_ref=graph["dispatch_ref"],
            observation_source="provider-reconcile",
            reported_status=status,
            provenance_refs=("provider:reconcile",),
        )
    )


def _confirm(store: Any, graph: dict[str, Any], *, proof_id: str) -> Any:
    work = graph["work"]
    run = graph["run"]
    attempt = graph["attempt"]
    action = graph["action"]
    proof = EvidenceArtifact(
        id=proof_id,
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
            "obligation_refs": ["verify.recovery"],
            "verifier_provenance": {
                "provider_id": "provider:verifier",
                "verifier_id": "verifier:recovery",
                "method": "closed-verification",
            },
        },
    )
    store.save_record(proof)
    return VerifiedOutcomeAuthority(store).confirm(
        action_ref=action.id,
        evidence_refs=[proof.id],
        expected_work_id=work.id,
        expected_run_id=run.id,
        expected_request_id=action.request_ref,
        expected_attempt_ref=attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=list(_VERSIONS),
    )


class _Policy:
    def __init__(self, action: str) -> None:
        self.action = action
        self.calls = 0

    def decide(self, basis: Any) -> str:
        self.calls += 1
        return self.action

    def __call__(self, basis: Any) -> str:
        return self.decide(basis)


class _NeverPolicy:
    calls = 0

    def decide(self, basis: Any) -> str:
        self.calls += 1
        raise AssertionError("current policy must not run for exact-basis replay")

    def __call__(self, basis: Any) -> str:
        return self.decide(basis)


def _request(
    module: Any,
    graph: dict[str, Any],
    *,
    observation_refs: tuple[str, ...],
    outcome_refs: tuple[str, ...] = (),
    policy_ref: str = "policy:recovery:v1",
) -> Any:
    return module.RecoveryDispositionCommitRequest(
        dispatch_commit_ref=graph["dispatch_ref"],
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        policy_ref=policy_ref,
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_001_exact_basis_replay_is_one_durable_decision(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"replay-{backend}") as store:
        graph = _seed_subject(store, f"replay-{backend}")
        obs_a = _observe(store, graph, instance_ref=f"obs:{backend}:a")
        obs_b = _observe(store, graph, instance_ref=f"obs:{backend}:b")
        policy = _Policy("hold-unresolved")
        first = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs_a.id, obs_b.id),
            ),
            policy=policy,
        )
        replay = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs_b.id, obs_a.id),
            ),
            policy=policy,
        )
        assert replay.id == first.id
        assert replay == first


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_002_observation_and_outcome_basis_order_is_canonical(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"order-{backend}") as store:
        graph = _seed_subject(store, f"order-{backend}")
        obs_a = _observe(store, graph, instance_ref=f"obs:{backend}:a")
        obs_b = _observe(store, graph, instance_ref=f"obs:{backend}:b")
        out_a = _confirm(store, graph, proof_id=f"proof:{backend}:a")
        out_b = _confirm(store, graph, proof_id=f"proof:{backend}:b")
        policy = _Policy("accept-objective-resolution")
        first = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs_a.id, obs_b.id),
                outcome_refs=(out_a.id, out_b.id),
            ),
            policy=policy,
        )
        reordered = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs_b.id, obs_a.id),
                outcome_refs=(out_b.id, out_a.id),
            ),
            policy=policy,
        )
        assert reordered.id == first.id


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_003_new_observation_creates_new_decision_without_supersession(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"new-observation-{backend}") as store:
        graph = _seed_subject(store, f"new-observation-{backend}")
        obs_a = _observe(store, graph, instance_ref=f"obs:{backend}:a")
        policy = _Policy("reconcile-again")
        first = store.commit_recovery_disposition(
            _request(module, graph, observation_refs=(obs_a.id,)),
            policy=policy,
        )
        obs_b = _observe(store, graph, instance_ref=f"obs:{backend}:b")
        second = store.commit_recovery_disposition(
            _request(module, graph, observation_refs=(obs_a.id, obs_b.id)),
            policy=policy,
        )
        assert second.id != first.id
        assert not getattr(first, "superseded", False)
        assert getattr(second, "supersedes_ref", None) is None


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_004_new_confirmed_outcome_identity_creates_new_decision(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"new-outcome-{backend}") as store:
        graph = _seed_subject(store, f"new-outcome-{backend}")
        obs = _observe(store, graph, instance_ref=f"obs:{backend}")
        out_a = _confirm(store, graph, proof_id=f"proof:{backend}:a")
        policy = _Policy("accept-objective-resolution")
        first = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs.id,),
                outcome_refs=(out_a.id,),
            ),
            policy=policy,
        )
        out_b = _confirm(store, graph, proof_id=f"proof:{backend}:b")
        second = store.commit_recovery_disposition(
            _request(
                module,
                graph,
                observation_refs=(obs.id,),
                outcome_refs=(out_b.id,),
            ),
            policy=policy,
        )
        assert out_a.metadata["objective_result"] == out_b.metadata["objective_result"]
        assert out_a.id != out_b.id
        assert second.id != first.id


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_005_policy_drift_replay_does_not_call_current_policy(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"policy-drift-{backend}") as store:
        graph = _seed_subject(store, f"policy-drift-{backend}")
        obs = _observe(store, graph, instance_ref=f"obs:{backend}")
        request = _request(module, graph, observation_refs=(obs.id,))
        first_policy = _Policy("hold-unresolved")
        first = store.commit_recovery_disposition(request, policy=first_policy)
        assert first_policy.calls == 1
        current_policy = _NeverPolicy()
        replay = store.commit_recovery_disposition(request, policy=current_policy)
        assert replay.id == first.id
        assert current_policy.calls == 0


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_006_same_basis_identity_cannot_rebind_decision_semantics(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    with _store(backend, tmp_path, f"rebound-{backend}") as store:
        graph = _seed_subject(store, f"rebound-{backend}")
        obs = _observe(store, graph, instance_ref=f"obs:{backend}")
        request = _request(module, graph, observation_refs=(obs.id,))
        first = store.commit_recovery_disposition(
            request,
            policy=_Policy("hold-unresolved"),
        )
        with pytest.raises(ValueError, match="rebound|identity|semantics|nondetermin"):
            store.commit_recovery_disposition(
                request,
                policy=_Policy("retry-idempotent"),
            )
        assert first.id


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3c_007_direct_recovery_disposition_event_append_is_denied(
    backend: str,
    tmp_path: Path,
) -> None:
    with (
        _store(backend, tmp_path, f"direct-event-{backend}") as store,
        pytest.raises(ValueError, match="RecoveryDisposition|commit_recovery_disposition"),
    ):
        store.append_event(
            Event(
                id=f"recovery_disposition_forged_{backend}",
                type="RecoveryDispositionRecorded",
                subject_ref="dispatch:forged",
                payload={
                    "schema": "recovery-disposition-v1",
                    "dispatch_commit_ref": "dispatch:forged",
                    "observation_refs": ["obs:forged"],
                    "policy_ref": "policy:forged",
                    "action": "retry-idempotent",
                },
            )
        )


def test_p3c_008_recovery_disposition_module_has_no_execution_or_terminal_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    source = inspect.getsource(module)
    forbidden = (
        "provider.invoke",
        "provider.reconcile",
        "RealityBoundary",
        "InvocationPermit",
        "commit_terminal",
        "CompletionAuthority",
        "ReviewObligation",
        "GovernedApplication",
        "APPLY_REVIEW_DISCHARGE",
    )
    for token in forbidden:
        assert token not in source


def test_p3c_a01_commit_request_does_not_accept_caller_recovery_mode() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    fields = set(module.RecoveryDispositionCommitRequest.__dataclass_fields__)
    assert "dispatch_commit_ref" in fields
    assert "observation_refs" in fields
    assert "outcome_refs" in fields
    assert "policy_ref" in fields
    assert "recovery_mode" not in fields
    assert "recovery_classification" not in fields
    assert "effect_semantics" not in fields
    assert "action" not in fields
