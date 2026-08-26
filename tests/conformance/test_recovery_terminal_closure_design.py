"""F1-B4 design freeze: recovery and terminal responsibilities remain non-substitutable."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation
from portable_runtime.governance.persistence import (
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.completion import CompletionAuthority

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("subject:v1",)
_SCHEME = "scheme:b4"
_CONTEXT = "use:deploy"


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"b4-design-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_execution(store: Any, suffix: str) -> tuple[Work, Run, Step, StepAttempt, Action]:
    work = Work(
        id=f"work_b4_{suffix}",
        title="F1-B4 design",
        metadata={"verification_scope": dict(_SCOPE), "work_version": 1},
    )
    run = Run(id=f"run_b4_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_b4_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_b4_{suffix}",
        step_id=step.id,
        provider_id="provider:executor",
        request_ref=f"request_b4_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_b4_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id=attempt.provider_id,
        request_ref=attempt.request_ref or "",
        status="succeeded",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    return work, run, step, attempt, action


def _confirm(store: Any, *, result: str, suffix: str) -> tuple[Work, Run, Step, OutcomeRecord]:
    work, run, step, attempt, action = _seed_execution(store, suffix)
    proof = EvidenceArtifact(
        id=f"evidence_b4_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        lifecycle_status="current",
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
    return work, run, step, outcome


def _governance_persistence(store: Any) -> Any:
    if isinstance(store, SQLiteStateStore):
        return SQLiteDistinctionGovernancePersistence(store)
    return InMemoryDistinctionGovernancePersistence(store)


def _open_blocking_q(store: Any, suffix: str) -> tuple[Any, ReviewObligation]:
    persistence = _governance_persistence(store)
    persistence.seed_state(
        _SCHEME,
        DistinctionState(
            qualification="qualified",
            activation="active",
            scope=frozenset({"repo/app", "repo/shared"}),
            partition=(frozenset({"repo/app"}), frozenset({"repo/shared"})),
            version=1,
        ),
    )
    obligation = ReviewObligation(
        id=f"review_b4_{suffix}",
        target=_SCHEME,
        trigger_ref=f"event_b4_{suffix}",
        basis_refs=(f"basis:b4:{suffix}",),
        context=_CONTEXT,
        blocking=True,
        closure_requirements=frozenset({"review_resolved"}),
    )
    persistence.commit_event_obligations(obligation.trigger_ref, (obligation,))
    return persistence, obligation


def _completion_proof(
    work: Work,
    run: Run,
    *,
    proof_id: str,
    proof_class: str | None = None,
    obligation_refs: list[str] | None = None,
) -> EvidenceArtifact:
    metadata: dict[str, object] = {
        "verification_result": {"result": "pass"},
        "work_id": work.id,
        "run_id": run.id,
        "verification_scope": dict(work.metadata.get("verification_scope", {})),
        "work_version": work.metadata.get("work_version", 1),
        "acceptance_criteria": list(work.acceptance_criteria),
        "obligation_refs": (
            obligation_refs
            if obligation_refs is not None
            else CompletionAuthority.required_obligation_refs(work)
        ),
    }
    if proof_class is not None:
        metadata["proof_class"] = proof_class
    return EvidenceArtifact(
        id=proof_id,
        kind="closed-verification",
        lifecycle_status="current",
        metadata=metadata,
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_001_confirmed_pass_is_not_terminal_completion(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"pass-{backend}") as store:
        work, run, _step, outcome = _confirm(store, result="pass", suffix=f"pass-{backend}")
        assert outcome.lifecycle_status == "confirmed"
        assert outcome.metadata["objective_result"] == "pass"
        assert store.get_work(work.id).status != "completed"
        assert store.get_run(run.id).status != "succeeded"


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_002_confirmed_fail_is_not_a_recovery_decision(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"fail-{backend}") as store:
        work, run, step, outcome = _confirm(store, result="fail", suffix=f"fail-{backend}")
        assert outcome.lifecycle_status == "confirmed"
        assert outcome.metadata["objective_result"] == "fail"
        assert store.get_work(work.id).status == work.status
        assert store.get_run(run.id).status == run.status
        assert store.get_step(step.id).status == step.status
        assert all("Recovery" not in event.type for event in store.list_events(outcome.id))


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_003_blocking_q_does_not_self_authorize_terminal_or_recovery(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"q-{backend}") as store:
        work = Work(id=f"work_b4_q_{backend}", title="Q independence")
        run = Run(id=f"run_b4_q_{backend}", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        persistence, obligation = _open_blocking_q(store, f"q-{backend}")
        assert obligation.id in persistence.list_obligations()
        assert store.get_work(work.id).status == "open"
        assert store.get_run(run.id).status == "running"


class _ReconcileProvider:
    def __init__(self, status: str) -> None:
        self.status = status

    async def reconcile(self, request_id: str) -> CapabilityResult:
        return CapabilityResult(
            request_id=request_id,
            provider_id="provider:reconcile",
            status=self.status,  # type: ignore[arg-type]
        )


class _Registry:
    def __init__(self, provider: _ReconcileProvider) -> None:
        self.provider = provider

    def get(self, provider_id: str) -> _ReconcileProvider:
        assert provider_id == "provider:reconcile"
        return self.provider


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["succeeded", "failed", "unknown"])
async def test_b4_004_reconciliation_result_is_not_objective_or_terminal(status: str) -> None:
    store = InMemoryStateStore()
    work = Work(id=f"work_b4_reconcile_{status}", title="reconcile")
    run = Run(id=f"run_b4_reconcile_{status}", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    boundary = RealityBoundary(store=store, registry=_Registry(_ReconcileProvider(status)))

    result = await boundary.reconcile("request:ambiguous", "provider:reconcile")

    assert result is not None
    assert result.status == status
    assert store.list_records("Outcome") == []
    assert store.get_work(work.id).status == "open"
    assert store.get_run(run.id).status == "running"


def test_b4_005_authority_modules_do_not_silently_cross_own_responsibilities() -> None:
    completion_source = inspect.getsource(
        importlib.import_module("portable_runtime.workflows.completion")
    )
    runtime_source = inspect.getsource(importlib.import_module("portable_runtime.core.runtime"))
    boundary_source = inspect.getsource(importlib.import_module("portable_runtime.core.boundary"))

    assert "ReviewObligation" not in completion_source
    assert "DistinctionGovernancePersistence" not in completion_source
    assert "VerifiedOutcomeAuthority" not in runtime_source
    assert "CompletionAuthority" not in runtime_source
    reconcile_source = boundary_source.split("    async def reconcile(", 1)[1].split(
        "    async def _execute_legacy", 1
    )[0]
    assert "VerifiedOutcomeAuthority" not in reconcile_source
    assert "CompletionAuthority" not in reconcile_source


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_006_unbound_blocking_q_is_not_a_global_terminal_veto(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"terminal-independent-{backend}") as store:
        work = Work(id=f"work_b4_terminal_{backend}", title="terminal independence")
        run = Run(id=f"run_b4_terminal_{backend}", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        persistence, obligation = _open_blocking_q(store, f"terminal-independent-{backend}")
        proof = _completion_proof(work, run, proof_id=f"proof_b4_terminal_{backend}")
        store.save_record(proof)

        completed = CompletionAuthority(store).authorize(
            work=work,
            run=run,
            verification_refs=[proof.id],
        )

        assert completed.status == "succeeded"
        assert store.get_work(work.id).status == "completed"
        assert obligation.id in persistence.list_obligations()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_007_revalidation_proof_does_not_discharge_governance_q(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"proof-not-discharge-{backend}") as store:
        persistence, obligation = _open_blocking_q(store, f"proof-not-discharge-{backend}")
        work = Work(
            id=f"work_b4_revalidation_{backend}",
            title="proof coverage is not Q discharge",
            metadata={
                "verification_scope": {},
                "work_version": 1,
                "revalidation_obligations": [obligation.id],
            },
        )
        run = Run(id=f"run_b4_revalidation_{backend}", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        proof = _completion_proof(
            work,
            run,
            proof_id=f"proof_b4_revalidation_{backend}",
            proof_class="revalidation",
            obligation_refs=[obligation.id],
        )
        store.save_record(proof)

        result = CompletionAuthority(store).authorize(
            work=work,
            run=run,
            verification_refs=[proof.id],
        )

        assert result.status == "succeeded"
        assert obligation.id in persistence.list_obligations()
        persisted = persistence.list_obligations()[obligation.id]
        assert persisted.closure_requirements == frozenset({"review_resolved"})


@_xfail("B4-A01: explicit terminal-governance applicability is not implemented")
def test_b4_a01_explicit_terminal_governance_requirement_fails_closed_on_unresolved_q() -> None:
    module = importlib.import_module("portable_runtime.workflows.terminal_governance")
    requirement = module.TerminalGovernanceRequirement(
        work_id="work:b4",
        run_id="run:b4",
        obligation_ref="review:b4",
        context=_CONTEXT,
        scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
    )
    decision = module.evaluate_terminal_governance_requirement(
        requirement=requirement,
        obligation_status="open",
    )
    assert decision.status == "blocked"
    assert not decision.terminal_authorized


@_xfail("B4-A02: durable recovery observation authority is not implemented")
def test_b4_a02_reconciliation_must_be_durable_before_recovery_judgment() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_closure")
    observation = module.RecoveryObservation(
        request_ref="request:b4",
        attempt_ref="attempt:b4",
        dispatch_commit_ref="dispatch:b4",
        source="provider-reconcile",
        result="succeeded",
    )
    assert observation.durable
    assert not observation.authoritative_outcome
    assert module.can_issue_recovery_disposition(observation_ref=None) is False


@_xfail("B4-A03: recovery disposition/application authority separation is not implemented")
def test_b4_a03_recovery_disposition_is_not_recovery_application() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_closure")
    disposition = module.RecoveryDisposition(
        observation_ref="recovery-observation:b4",
        action="retry-same-idempotency-identity",
        policy_ref="recovery-policy:v1",
    )
    assert disposition.action == "retry-same-idempotency-identity"
    assert module.recovery_application_for(disposition) is None
