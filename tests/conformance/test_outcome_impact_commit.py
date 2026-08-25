"""F1-B3 P2b: durable impact judgment/disposition is store-owned and replay-stable."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.governance.outcome_impact import OutcomeGovernanceDependency
from portable_runtime.governance.outcome_impact_commit import (
    OUTCOME_DISPOSITION_EVENT,
    OUTCOME_IMPACT_JUDGMENT_EVENT,
    OutcomeImpactCommitRequest,
)
from portable_runtime.governance.outcome_impact_judgment import OutcomeImpact, OutcomeImpactJudgment
from portable_runtime.governance.persistence import (
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.revalidation import RevalidationDisposition
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_GOVERNED_SCOPE = frozenset({"repo/app", "repo/shared"})
_VERSIONS = ("subject:v1",)


@dataclass
class _ImpactPolicy:
    policy_ref: str
    impact: OutcomeImpact
    calls: int = 0

    def judge(self, outcome, applicability):
        self.calls += 1
        return self.impact, (f"impact-policy:{self.policy_ref}", outcome.id)


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
            rationale_refs=[f"disposition-policy:{self.policy_ref}", judgment.outcome_ref],
        )


@contextmanager
def _store(backend: str, tmp_path: Path) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"impact-{backend}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_verified(store: Any, suffix: str = "commit"):
    work = Work(id=f"work_b3_{suffix}", title="impact commit", metadata={"work_version": 1})
    run = Run(id=f"run_b3_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_b3_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_b3_{suffix}",
        step_id=step.id,
        provider_id="provider:executor",
        request_ref=f"request_b3_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_b3_{suffix}",
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
        id=f"evidence_b3_{suffix}",
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
    dependency = OutcomeGovernanceDependency(
        outcome_ref=outcome.id,
        action_ref=action.id,
        scheme_id="scheme:b3",
        context="use:deploy",
        scope=_GOVERNED_SCOPE,
        subject_version_refs=_VERSIONS,
        basis_refs=("dependency:b3",),
    )
    request = OutcomeImpactCommitRequest(
        event_ref=event.id,
        dependency=dependency,
        context="use:deploy",
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
    )
    return outcome, event, request


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p2b_commit_is_durable_deterministic_and_does_not_process_trigger(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as store:
        _outcome, event, request = _seed_verified(store, backend)
        impact = _ImpactPolicy("impact-policy:v1", "qualification-challenged")
        disposition = _DispositionPolicy("disposition-policy:v1", "block-next-use")
        committed = store.commit_outcome_impact_judgment(request, impact, disposition)

        assert committed.judgment.impact == "qualification-challenged"
        assert committed.disposition.action == "block-next-use"
        assert not committed.replayed
        assert impact.calls == 1
        assert disposition.calls == 1
        assert store.get_event(committed.judgment_event_ref).type == OUTCOME_IMPACT_JUDGMENT_EVENT
        assert store.get_event(committed.disposition_event_ref).type == OUTCOME_DISPOSITION_EVENT

        persistence = (
            InMemoryDistinctionGovernancePersistence(store)
            if backend == "memory"
            else SQLiteDistinctionGovernancePersistence(store)
        )
        assert persistence.processed_event_obligation_ids(event.id) is None
        assert persistence.list_obligations() == {}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p2b_replay_uses_original_durable_judgment_not_current_policy(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as store:
        _outcome, _event, request = _seed_verified(store, f"replay-{backend}")
        first_impact = _ImpactPolicy("impact-policy:v1", "revalidation-required")
        first_disposition = _DispositionPolicy("disposition-policy:v1", "require-human-review")
        first = store.commit_outcome_impact_judgment(request, first_impact, first_disposition)

        changed_impact = _ImpactPolicy("impact-policy:v2", "no-governance-impact")
        changed_disposition = _DispositionPolicy("disposition-policy:v2", "none")
        replay = store.commit_outcome_impact_judgment(request, changed_impact, changed_disposition)

        assert replay.replayed
        assert replay.key_digest == first.key_digest
        assert replay.judgment == first.judgment
        assert replay.disposition == first.disposition
        assert changed_impact.calls == 0
        assert changed_disposition.calls == 0


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p2b_direct_authority_event_append_is_denied(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as store:
        forged = Event(
            id="event_outcome_impact_forged",
            type=OUTCOME_IMPACT_JUDGMENT_EVENT,
            subject_ref="outcome:forged",
            payload={"binding_digest": "forged"},
        )
        with pytest.raises(ValueError, match="commit_outcome_impact_judgment"):
            store.append_event(forged)
        assert store.get_event(forged.id) is None


def test_b3_p2b_authority_event_failure_rolls_back_entire_durable_judgment() -> None:
    class FailingStore(InMemoryStateStore):
        def append_event(self, value: Event) -> None:
            if value.type == OUTCOME_DISPOSITION_EVENT:
                raise RuntimeError("simulated disposition journal failure")
            super().append_event(value)

    store = FailingStore()
    _outcome, _event, request = _seed_verified(store, "atomicity")
    impact = _ImpactPolicy("impact-policy:v1", "revalidation-required")
    disposition = _DispositionPolicy("disposition-policy:v1", "block-next-use")
    with pytest.raises(RuntimeError, match="disposition journal failure"):
        store.commit_outcome_impact_judgment(request, impact, disposition)
    assert not any(
        event.type in {OUTCOME_IMPACT_JUDGMENT_EVENT, OUTCOME_DISPOSITION_EVENT}
        for event in store.list_events()
    )


def test_b3_p2b_forged_trigger_or_mismatched_applicability_writes_no_judgment() -> None:
    store = InMemoryStateStore()
    _outcome, _event, request = _seed_verified(store, "reject")
    impact = _ImpactPolicy("impact-policy:v1", "revalidation-required")
    disposition = _DispositionPolicy("disposition-policy:v1", "block-next-use")

    wrong = OutcomeImpactCommitRequest(
        event_ref=request.event_ref,
        dependency=OutcomeGovernanceDependency(
            **{**request.dependency.__dict__, "context": "use:other"}
        ),
        context=request.context,
        requested_scope=request.requested_scope,
        subject_version_refs=request.subject_version_refs,
    )
    with pytest.raises(ValueError, match="applicable dependency"):
        store.commit_outcome_impact_judgment(wrong, impact, disposition)
    assert not any(
        event.type in {OUTCOME_IMPACT_JUDGMENT_EVENT, OUTCOME_DISPOSITION_EVENT}
        for event in store.list_events()
    )
