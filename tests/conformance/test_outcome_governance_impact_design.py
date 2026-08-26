"""F1-B3 design freeze: confirmed Outcome authority is not governance authority."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.revalidation import project_review_obligation
from portable_runtime.records.models import Assertion, EvidenceArtifact, OutcomeRecord
from portable_runtime.records.qualification_transition import (
    QUALIFICATION_TRANSITION_EVENT_TYPE,
    build_qualification_transition_event,
)
from portable_runtime.records.revalidation import AffectedAssessment, CHANGE_TYPES, RevalidationDisposition
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.memory import InMemoryStateStore

_SCHEME = "scheme:b3"
_CONTEXT = "use:deploy"
_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ["subject:v1"]


def _seed_execution(store: InMemoryStateStore, suffix: str) -> tuple[Work, Run, StepAttempt, Action]:
    work = Work(
        id=f"work_b3_{suffix}",
        title="F1-B3 design",
        metadata={"verification_scope": dict(_SCOPE), "work_version": 1},
    )
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
    return work, run, attempt, action


def _confirm(
    store: InMemoryStateStore,
    *,
    result: str,
    suffix: str,
) -> tuple[Work, Run, Action, OutcomeRecord]:
    work, run, attempt, action = _seed_execution(store, suffix)
    proof = EvidenceArtifact(
        id=f"evidence_b3_{suffix}",
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
    return work, run, action, outcome


def _seed_governance(
    store: InMemoryStateStore,
) -> tuple[InMemoryDistinctionGovernancePersistence, DistinctionState]:
    persistence = InMemoryDistinctionGovernancePersistence(store)
    state = DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"repo/app", "repo/shared"}),
        partition=(frozenset({"repo/app"}), frozenset({"repo/shared"})),
        version=7,
    )
    persistence.seed_state(_SCHEME, state)
    return persistence, state


def _open_existing_review(
    persistence: InMemoryDistinctionGovernancePersistence,
    *,
    suffix: str,
) -> ReviewObligation:
    obligation = ReviewObligation(
        id=f"review_b3_{suffix}",
        target=_SCHEME,
        trigger_ref=f"event_preexisting_{suffix}",
        basis_refs=(f"basis:{suffix}",),
        context=_CONTEXT,
        blocking=True,
        closure_requirements=frozenset({"basis_checked"}),
    )
    persistence.commit_event_obligations(obligation.trigger_ref, (obligation,))
    return obligation


def _future_module() -> Any:
    return importlib.import_module("portable_runtime.governance.outcome_impact")


def _confirmed_claim(result: str = "pass", suffix: str = "future") -> OutcomeRecord:
    return OutcomeRecord(
        id=f"outcome_b3_{suffix}",
        action_ref=f"action_b3_{suffix}",
        evidence_refs=[f"evidence_b3_{suffix}"],
        lifecycle_status="confirmed",
        metadata={
            "objective_result": result,
            "work_id": f"work_b3_{suffix}",
            "run_id": f"run_b3_{suffix}",
            "request_id": f"request_b3_{suffix}",
            "attempt_ref": f"attempt_b3_{suffix}",
            "verification_scope": dict(_SCOPE),
            "subject_version_refs": list(_VERSIONS),
            "verification_binding_digest": f"digest:{suffix}",
        },
    )


def test_b3_design_outcome_is_not_an_existing_revalidation_change_type() -> None:
    assert "outcome" not in CHANGE_TYPES
    assert "confirmed-outcome" not in CHANGE_TYPES


def test_b3_design_assertion_epistemic_axis_is_not_distinction_qualification() -> None:
    assertion = Assertion(
        id="assertion_b3_axis",
        statement="objective effect remains valid",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    after = assertion.model_copy(update={"epistemic_status": "revalidation-required", "version": 2})
    event = build_qualification_transition_event(
        assertion,
        after,
        reason_refs=["outcome:b3-axis"],
        event_id="event_b3_assertion_axis",
    )
    distinction = DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"repo/app"}),
        partition=(frozenset({"repo/app"}),),
        version=3,
    )
    assert event.type == QUALIFICATION_TRANSITION_EVENT_TYPE
    assert distinction.qualification == "qualified"
    source = inspect.getsource(importlib.import_module("portable_runtime.records.qualification_transition"))
    assert "DistinctionState" not in source
    assert "APPLY_QUALIFICATION" not in source


def test_b3_001_confirmed_pass_without_explicit_dependency_has_no_governance_effect() -> None:
    store = InMemoryStateStore()
    persistence, state = _seed_governance(store)
    _confirm(store, result="pass", suffix="pass-no-dependency")
    assert persistence.list_obligations() == {}
    assert persistence.get_state(_SCHEME) == state


def test_b3_002_confirmed_fail_without_explicit_dependency_does_not_disqualify_or_reopen() -> None:
    store = InMemoryStateStore()
    persistence, state = _seed_governance(store)
    _confirm(store, result="fail", suffix="fail-no-dependency")
    assert persistence.list_obligations() == {}
    assert persistence.get_state(_SCHEME) == state
    assert persistence.get_state(_SCHEME).qualification == "qualified"  # type: ignore[union-attr]
    assert persistence.get_state(_SCHEME).activation == "active"  # type: ignore[union-attr]


def test_b3_003_mismatched_dependency_scope_version_or_context_fails_closed() -> None:
    module = _future_module()
    dependency = module.OutcomeGovernanceDependency(
        outcome_ref="outcome_b3_future",
        action_ref="action_b3_future",
        scheme_id=_SCHEME,
        context=_CONTEXT,
        scope=frozenset({"repo/app"}),
        subject_version_refs=tuple(_VERSIONS),
        basis_refs=("basis:explicit",),
    )
    applicability = module.resolve_outcome_applicability(
        outcome=_confirmed_claim(),
        dependency=dependency,
        context="use:other",
        requested_scope=frozenset({"repo/other"}),
        subject_version_refs=("subject:v2",),
    )
    assert applicability.status == "mismatch"
    assert not applicability.applicable


@pytest.mark.parametrize("impact", ["no-governance-impact", "recovery-only"])
def test_b3_004_no_governance_or_recovery_only_impact_opens_no_review(impact: str) -> None:
    module = importlib.import_module("portable_runtime.governance.outcome_impact_lifecycle")
    source = inspect.getsource(module.OutcomeGovernanceImpactLifecycle.observe_outcome_confirmed)
    assert 'impact.judgment.impact in {"no-governance-impact", "recovery-only"}' in source
    assert 'impact.disposition.action not in {"none", "warn"}' in source
    assert "continue" in source


@pytest.mark.parametrize("action", ["block-next-use", "require-human-review", "reopen"])
def test_b3_005_blocking_disposition_may_open_q_but_does_not_mutate_state(action: str) -> None:
    from portable_runtime.governance.revalidation import project_review_obligation_from_disposition

    store = InMemoryStateStore()
    persistence, state = _seed_governance(store)
    projection = project_review_obligation_from_disposition(
        trigger_event_ref="event_outcome_confirmed_required",
        target=_SCHEME,
        context=_CONTEXT,
        disposition=RevalidationDisposition(
            action=action,
            policy_ref="policy:b3:required",
            rationale_refs=["judgment:b3:required"],
        ),
        basis_refs=(
            "outcome:b3:required",
            "event_objective_verification:b3:required",
            "event_outcome_impact:b3:required",
            "dependency:b3:required",
            "event_outcome_disposition:b3:required",
            "policy:b3:required",
        ),
        persistence=persistence,
    )
    assert projection.status == "ready"
    assert projection.obligation is not None
    assert projection.obligation.trigger_ref == "event_outcome_confirmed_required"
    assert persistence.list_obligations() == {}
    assert persistence.get_state(_SCHEME) == state


def test_b3_006_reopen_disposition_is_not_reopen_authority() -> None:
    store = InMemoryStateStore()
    persistence, state = _seed_governance(store)
    assessment = AffectedAssessment(
        change_ref="outcome:design-placeholder",
        affected_ref=_SCHEME,
        required_action="reopen",
        revalidation_disposition=RevalidationDisposition(
            action="reopen",
            policy_ref="b3-design-profile",
            rationale_refs=["outcome:design-placeholder"],
        ),
    )
    projection = project_review_obligation(
        assessment,
        event_ref="event_b3_reopen_projection",
        context=_CONTEXT,
        persistence=persistence,
    )
    assert projection.status == "ready"
    assert projection.obligation is not None
    assert "reopen_resolved" in projection.obligation.closure_requirements
    assert persistence.list_obligations() == {}
    assert persistence.get_state(_SCHEME) == state


def test_b3_007_confirmed_pass_does_not_discharge_existing_review() -> None:
    store = InMemoryStateStore()
    persistence, _state = _seed_governance(store)
    obligation = _open_existing_review(persistence, suffix="pass")
    _confirm(store, result="pass", suffix="pass-existing-q")
    assert obligation.id in persistence.list_obligations()


def test_b3_008_confirmed_fail_does_not_satisfy_existing_review_closure() -> None:
    store = InMemoryStateStore()
    persistence, _state = _seed_governance(store)
    obligation = _open_existing_review(persistence, suffix="fail")
    _confirm(store, result="fail", suffix="fail-existing-q")
    persisted = persistence.list_obligations()[obligation.id]
    assert persisted.closure_requirements == frozenset({"basis_checked"})


def test_b3_009_same_outcome_confirmed_event_replay_is_idempotent() -> None:
    from portable_runtime.governance.revalidation import project_review_obligation_from_disposition

    store = InMemoryStateStore()
    persistence, _state = _seed_governance(store)
    event_ref = "event_outcome_b3_same"
    projection = project_review_obligation_from_disposition(
        trigger_event_ref=event_ref,
        target=_SCHEME,
        context=_CONTEXT,
        disposition=RevalidationDisposition(
            action="block-next-use",
            policy_ref="policy:b3:replay",
            rationale_refs=["judgment:b3:replay"],
        ),
        basis_refs=("outcome:b3:replay", "judgment:b3:replay"),
        persistence=persistence,
    )
    assert projection.obligation is not None
    first = persistence.commit_event_obligations(event_ref, (projection.obligation,))
    second = persistence.commit_event_obligations(event_ref, (projection.obligation,))
    assert second == first
    assert tuple(persistence.list_obligations()) == first


def test_b3_010_new_verification_closure_is_not_old_event_replay() -> None:
    from portable_runtime.governance.revalidation import project_review_obligation_from_disposition

    store = InMemoryStateStore()
    persistence, _state = _seed_governance(store)
    ids: list[str] = []
    for event_ref in ("event_outcome_b3_v1", "event_outcome_b3_v2"):
        projection = project_review_obligation_from_disposition(
            trigger_event_ref=event_ref,
            target=_SCHEME,
            context=_CONTEXT,
            disposition=RevalidationDisposition(
                action="background-revalidate",
                policy_ref="policy:b3:new-event",
                rationale_refs=[event_ref],
            ),
            basis_refs=(f"outcome:{event_ref}",),
            persistence=persistence,
        )
        assert projection.obligation is not None
        committed = persistence.commit_event_obligations(event_ref, (projection.obligation,))
        ids.append(committed[0])
    assert ids[0] != ids[1]
    assert len(persistence.list_obligations()) == 2


def test_b3_011_unavailable_impact_judgment_is_not_no_impact() -> None:
    from portable_runtime.core.models import Event
    from portable_runtime.governance.outcome_impact import (
        OutcomeConfirmedTriggerResolution,
        OutcomeGovernanceApplicability,
    )
    from portable_runtime.governance.outcome_impact_judgment import evaluate_outcome_impact

    outcome = _confirmed_claim(result="fail", suffix="unavailable-impact")
    event = Event(
        id="event_outcome_b3_unavailable_impact",
        type="OutcomeConfirmed",
        subject_ref=outcome.id,
    )
    trigger = OutcomeConfirmedTriggerResolution(
        status="ready",
        event_ref=event.id,
        reason="required-test-authoritative-trigger",
        event=event,
        outcome=outcome,
    )
    applicability = OutcomeGovernanceApplicability(
        status="applicable",
        outcome_ref=outcome.id,
        action_ref=outcome.action_ref,
        scheme_id=_SCHEME,
        context=_CONTEXT,
        governed_scope=frozenset({"repo/app"}),
        subject_version_refs=tuple(_VERSIONS),
        basis_refs=("basis:explicit",),
        reason="explicit-dependency-matched",
    )

    class UnavailablePolicy:
        policy_ref = "policy:b3:unavailable"

        def judge(self, _outcome, _applicability):
            return None

    result = evaluate_outcome_impact(
        trigger=trigger,
        applicability=applicability,
        policy=UnavailablePolicy(),
    )
    assert result.status == "unavailable"
    assert result.impact == "unknown"
    assert result.impact != "no-governance-impact"
    assert result.judgment is None


def test_b3_012_confirmed_outcome_does_not_gain_terminal_or_recovery_authority() -> None:
    store = InMemoryStateStore()
    work, run, _action, _outcome = _confirm(store, result="pass", suffix="nonterminal")
    assert store.get_work(work.id).status != "completed"  # type: ignore[union-attr]
    assert store.get_run(run.id).status != "succeeded"  # type: ignore[union-attr]
    source = inspect.getsource(importlib.import_module("portable_runtime.records.verified_outcome"))
    assert "CompletionAuthority" not in source
    assert "recovery" not in source.lower()
    assert "governance" not in source.lower()
