"""F1-B3 P3: authoritative Outcome impact stops at existing ReviewObligation authority boundary."""

from __future__ import annotations

import ast
import importlib
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.governance.distinction import DistinctionState
from portable_runtime.governance.outcome_impact import OutcomeGovernanceDependency
from portable_runtime.governance.outcome_impact_judgment import OutcomeImpact, OutcomeImpactJudgment
from portable_runtime.governance.outcome_impact_lifecycle import OutcomeGovernanceImpactLifecycle
from portable_runtime.governance.persistence import (
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.revalidation import RevalidationDisposition
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_CONTEXT = "use:deploy"
_SCHEME = "scheme:b3"
_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("subject:v1",)


@dataclass
class _ImpactPolicy:
    policy_ref: str
    impact: OutcomeImpact
    calls: int = 0

    def judge(self, outcome, applicability):
        self.calls += 1
        return self.impact, (f"impact:{self.policy_ref}", outcome.id)


@dataclass
class _DispositionPolicy:
    policy_ref: str
    action: str
    calls: int = 0

    def decide(self, judgment: OutcomeImpactJudgment) -> RevalidationDisposition:
        self.calls += 1
        return RevalidationDisposition(
            action=self.action,  # type: ignore[arg-type]
            policy_ref=self.policy_ref,
            rationale_refs=[f"disposition:{self.policy_ref}", judgment.outcome_ref],
        )


@contextmanager
def _store_and_persistence(backend: str, tmp_path: Path) -> Iterator[tuple[Any, Any]]:
    if backend == "memory":
        store = InMemoryStateStore()
        yield store, InMemoryDistinctionGovernancePersistence(store)
        return
    store = SQLiteStateStore(tmp_path / f"b3-lifecycle-{backend}.db")
    try:
        yield store, SQLiteDistinctionGovernancePersistence(store)
    finally:
        store.close()


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"repo/app", "repo/shared"}),
        partition=(frozenset({"repo/app"}), frozenset({"repo/shared"})),
        version=9,
    )


def _verified(store: Any, suffix: str):
    work = Work(id=f"work_b3_lifecycle_{suffix}", title="lifecycle", metadata={"work_version": 1})
    run = Run(id=f"run_b3_lifecycle_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_b3_lifecycle_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_b3_lifecycle_{suffix}",
        step_id=step.id,
        provider_id="provider:executor",
        request_ref=f"request_b3_lifecycle_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_b3_lifecycle_{suffix}",
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
    proof = EvidenceArtifact(
        id=f"evidence_b3_lifecycle_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        lifecycle_status="current",
        metadata={
            "verification_result": {"result": "fail"},
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
    event = next(event for event in store.list_events(outcome.id) if event.type == "OutcomeConfirmed")
    accepted = next(
        event for event in store.list_events(outcome.id) if event.type == "ObjectiveVerificationAccepted"
    )
    dependency = OutcomeGovernanceDependency(
        outcome_ref=outcome.id,
        action_ref=action.id,
        scheme_id=_SCHEME,
        context=_CONTEXT,
        scope=frozenset({"repo/app", "repo/shared"}),
        subject_version_refs=_VERSIONS,
        basis_refs=(f"dependency:{suffix}",),
    )
    return outcome, event, accepted, dependency


def _observe(
    lifecycle: OutcomeGovernanceImpactLifecycle,
    *,
    event: Event,
    dependency: OutcomeGovernanceDependency,
    impact: _ImpactPolicy,
    disposition: _DispositionPolicy,
):
    return lifecycle.observe_outcome_confirmed(
        event_ref=event.id,
        dependencies=(dependency,),
        context=_CONTEXT,
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
        impact_policy_for=lambda _dependency: impact,
        disposition_policy_for=lambda _dependency: disposition,
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize(
    ("impact_name", "action"),
    [("no-governance-impact", "none"), ("recovery-only", "warn")],
)
def test_b3_004_resolved_non_governance_impacts_open_no_review(
    backend: str,
    impact_name: OutcomeImpact,
    action: str,
    tmp_path: Path,
) -> None:
    with _store_and_persistence(backend, tmp_path) as (store, persistence):
        persistence.seed_state(_SCHEME, _state())
        _outcome, event, _accepted, dependency = _verified(store, f"noq-{backend}-{impact_name}")
        result = _observe(
            OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence),
            event=event,
            dependency=dependency,
            impact=_ImpactPolicy("impact-policy:noq", impact_name),
            disposition=_DispositionPolicy("disposition-policy:noq", action),
        )
        assert result.status == "processed"
        assert result.opened_obligations == ()
        assert persistence.processed_event_obligation_ids(event.id) == ()
        assert persistence.list_obligations() == {}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("action", ["block-next-use", "require-human-review", "reopen"])
def test_b3_005_review_disposition_opens_q_without_mutating_distinction_state(
    backend: str,
    action: str,
    tmp_path: Path,
) -> None:
    with _store_and_persistence(backend, tmp_path) as (store, persistence):
        state = _state()
        persistence.seed_state(_SCHEME, state)
        outcome, event, accepted, dependency = _verified(store, f"q-{backend}-{action}")
        result = _observe(
            OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence),
            event=event,
            dependency=dependency,
            impact=_ImpactPolicy("impact-policy:q", "qualification-challenged"),
            disposition=_DispositionPolicy("disposition-policy:q", action),
        )
        assert result.status == "processed"
        assert len(result.opened_obligations) == 1
        obligation = result.opened_obligations[0]
        assert obligation.trigger_ref == event.id
        assert obligation.target == _SCHEME
        assert outcome.id in obligation.basis_refs
        assert accepted.id in obligation.basis_refs
        assert dependency.basis_refs[0] in obligation.basis_refs
        assert any(ref.startswith("event_outcome_impact_") for ref in obligation.basis_refs)
        assert any(ref.startswith("event_outcome_disposition_") for ref in obligation.basis_refs)
        assert "disposition-policy:q" in obligation.basis_refs
        assert persistence.get_state(_SCHEME) == state


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_009_same_outcome_confirmed_event_replay_is_idempotent(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store_and_persistence(backend, tmp_path) as (store, persistence):
        persistence.seed_state(_SCHEME, _state())
        _outcome, event, _accepted, dependency = _verified(store, f"replay-{backend}")
        lifecycle = OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence)
        impact = _ImpactPolicy("impact-policy:replay", "revalidation-required")
        disposition = _DispositionPolicy("disposition-policy:replay", "block-next-use")
        first = _observe(lifecycle, event=event, dependency=dependency, impact=impact, disposition=disposition)
        second = _observe(lifecycle, event=event, dependency=dependency, impact=impact, disposition=disposition)
        assert first.status == "processed"
        assert second.status == "already-processed"
        assert second.already_processed_obligation_ids == tuple(q.id for q in first.opened_obligations)
        assert len(persistence.list_obligations()) == 1
        assert impact.calls == 1
        assert disposition.calls == 1


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_010_new_confirmed_outcome_identity_is_new_governance_event(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store_and_persistence(backend, tmp_path) as (store, persistence):
        persistence.seed_state(_SCHEME, _state())
        lifecycle = OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence)
        opened_ids: list[str] = []
        event_ids: list[str] = []
        for suffix in ("closure-a", "closure-b"):
            _outcome, event, _accepted, dependency = _verified(store, f"{backend}-{suffix}")
            result = _observe(
                lifecycle,
                event=event,
                dependency=dependency,
                impact=_ImpactPolicy(f"impact-policy:{suffix}", "revalidation-required"),
                disposition=_DispositionPolicy(f"disposition-policy:{suffix}", "background-revalidate"),
            )
            assert result.status == "processed"
            opened_ids.append(result.opened_obligations[0].id)
            event_ids.append(event.id)
        assert event_ids[0] != event_ids[1]
        assert opened_ids[0] != opened_ids[1]
        assert len(persistence.list_obligations()) == 2


def test_b3_p3_projection_failure_keeps_event_unprocessed_and_reuses_durable_judgment() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    _outcome, event, _accepted, dependency = _verified(store, "projection-retry")
    lifecycle = OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence)
    first_impact = _ImpactPolicy("impact-policy:original", "qualification-challenged")
    first_disposition = _DispositionPolicy("disposition-policy:original", "block-next-use")
    first = _observe(
        lifecycle,
        event=event,
        dependency=dependency,
        impact=first_impact,
        disposition=first_disposition,
    )
    assert first.status == "unavailable"
    assert persistence.processed_event_obligation_ids(event.id) is None
    assert len(first.committed_impacts) == 1

    persistence.seed_state(_SCHEME, _state())
    changed_impact = _ImpactPolicy("impact-policy:changed", "no-governance-impact")
    changed_disposition = _DispositionPolicy("disposition-policy:changed", "none")
    second = _observe(
        lifecycle,
        event=event,
        dependency=dependency,
        impact=changed_impact,
        disposition=changed_disposition,
    )
    assert second.status == "processed"
    assert second.opened_obligations[0].blocking
    assert second.committed_impacts[0].judgment.policy_ref == "impact-policy:original"
    assert second.committed_impacts[0].disposition.policy_ref == "disposition-policy:original"
    assert changed_impact.calls == 0
    assert changed_disposition.calls == 0


def test_b3_a01_forged_trigger_opens_no_q_and_is_not_processed() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state(_SCHEME, _state())
    forged = Event(
        id="event_b3_forged_outcome_confirmed",
        type="OutcomeConfirmed",
        subject_ref="outcome:forged",
        payload={"authoritative_outcome": True, "verification_binding_digest": "forged"},
    )
    store.append_event(forged)
    dependency = OutcomeGovernanceDependency(
        outcome_ref="outcome:forged",
        action_ref="action:forged",
        scheme_id=_SCHEME,
        context=_CONTEXT,
        scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
        basis_refs=("dependency:forged",),
    )
    result = _observe(
        OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence),
        event=forged,
        dependency=dependency,
        impact=_ImpactPolicy("impact-policy:forged", "qualification-challenged"),
        disposition=_DispositionPolicy("disposition-policy:forged", "block-next-use"),
    )
    assert result.status == "unavailable"
    assert persistence.processed_event_obligation_ids(forged.id) is None
    assert persistence.list_obligations() == {}


def test_b3_p3_no_explicit_dependency_opens_no_q_and_does_not_guess_processed() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state(_SCHEME, _state())
    _outcome, event, _accepted, _dependency = _verified(store, "not-declared")
    result = OutcomeGovernanceImpactLifecycle(store=store, persistence=persistence).observe_outcome_confirmed(
        event_ref=event.id,
        dependencies=(),
        context=_CONTEXT,
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
        impact_policy_for=lambda _dependency: _ImpactPolicy("unused", "unknown"),
        disposition_policy_for=lambda _dependency: _DispositionPolicy("unused", "none"),
    )
    assert result.status == "not-declared"
    assert persistence.processed_event_obligation_ids(event.id) is None
    assert persistence.list_obligations() == {}


def test_b3_p3_module_has_no_decision_application_or_terminal_authority() -> None:
    module = importlib.import_module("portable_runtime.governance.outcome_impact_lifecycle")
    source = inspect.getsource(module)
    tree = ast.parse(source)
    forbidden = {
        "GovernanceDecision",
        "GovernedApplication",
        "apply_state_transition",
        "apply_review_discharge",
        "CompletionAuthority",
        "commit_terminal",
        "commit_review_discharge",
        "commit_state_application",
    }
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert forbidden.isdisjoint(referenced)
