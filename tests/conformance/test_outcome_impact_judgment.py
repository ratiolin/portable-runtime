"""F1-B3 P2a: impact judgment is pure, explicit-policy, and fail-closed."""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass

from portable_runtime.core.models import Event
from portable_runtime.governance.outcome_impact import (
    OutcomeConfirmedTriggerResolution,
    OutcomeGovernanceApplicability,
)
from portable_runtime.governance.outcome_impact_judgment import (
    OutcomeImpact,
    evaluate_outcome_impact,
)
from portable_runtime.records.models import OutcomeRecord


@dataclass(frozen=True)
class _Policy:
    policy_ref: str
    result: OutcomeImpact | None

    def judge(self, outcome, applicability):
        if self.result is None:
            return None
        return self.result, (f"policy:{self.policy_ref}", f"outcome:{outcome.id}")


def _trigger(objective_result: str = "pass") -> OutcomeConfirmedTriggerResolution:
    outcome = OutcomeRecord(
        id=f"outcome_b3_judgment_{objective_result}",
        action_ref=f"action_b3_judgment_{objective_result}",
        evidence_refs=[f"evidence:{objective_result}"],
        lifecycle_status="confirmed",
        metadata={"objective_result": objective_result},
    )
    event = Event(
        id=f"event_outcome_confirmed_b3_judgment_{objective_result}",
        type="OutcomeConfirmed",
        subject_ref=outcome.id,
    )
    return OutcomeConfirmedTriggerResolution(
        status="ready",
        event_ref=event.id,
        reason="test-authoritative-trigger",
        event=event,
        outcome=outcome,
    )


def _applicability(trigger: OutcomeConfirmedTriggerResolution) -> OutcomeGovernanceApplicability:
    assert trigger.outcome is not None
    return OutcomeGovernanceApplicability(
        status="applicable",
        outcome_ref=trigger.outcome.id,
        action_ref=trigger.outcome.action_ref,
        scheme_id="scheme:b3",
        context="use:deploy",
        governed_scope=frozenset({"repo/app"}),
        subject_version_refs=("subject:v1",),
        basis_refs=("dependency:b3",),
        reason="explicit-dependency-matched",
    )


def test_b3_p2a_explicit_policy_produces_pure_impact_judgment() -> None:
    trigger = _trigger("pass")
    result = evaluate_outcome_impact(
        trigger=trigger,
        applicability=_applicability(trigger),
        policy=_Policy("policy:b3:review", "revalidation-required"),
    )
    assert result.status == "ready"
    assert result.impact == "revalidation-required"
    assert result.judgment is not None
    assert result.judgment.policy_ref == "policy:b3:review"
    assert result.judgment.trigger_event_ref == trigger.event_ref
    assert result.judgment.applicability_basis_refs == ("dependency:b3",)


def test_b3_p2a_objective_result_has_no_builtin_governance_mapping() -> None:
    failed = _trigger("fail")
    failed_result = evaluate_outcome_impact(
        trigger=failed,
        applicability=_applicability(failed),
        policy=_Policy("policy:b3:fail-no-impact", "no-governance-impact"),
    )
    passed = _trigger("pass")
    passed_result = evaluate_outcome_impact(
        trigger=passed,
        applicability=_applicability(passed),
        policy=_Policy("policy:b3:pass-challenge", "qualification-challenged"),
    )
    assert failed_result.impact == "no-governance-impact"
    assert passed_result.impact == "qualification-challenged"


def test_b3_011_unavailable_impact_judgment_is_not_no_impact() -> None:
    trigger = _trigger("fail")
    result = evaluate_outcome_impact(
        trigger=trigger,
        applicability=_applicability(trigger),
        policy=_Policy("policy:b3:unavailable", None),
    )
    assert result.status == "unavailable"
    assert result.impact == "unknown"
    assert result.judgment is None


def test_b3_p2a_missing_authoritative_trigger_or_applicability_fails_closed() -> None:
    trigger = _trigger()
    unavailable_trigger = OutcomeConfirmedTriggerResolution(
        status="unavailable",
        event_ref=trigger.event_ref,
        reason="authority-graph-mismatch",
        event=trigger.event,
        outcome=trigger.outcome,
    )
    assert evaluate_outcome_impact(
        trigger=unavailable_trigger,
        applicability=_applicability(trigger),
        policy=_Policy("policy:b3", "revalidation-required"),
    ).status == "unavailable"

    applicability = _applicability(trigger)
    not_declared = OutcomeGovernanceApplicability(
        **{**applicability.__dict__, "status": "not-declared", "scheme_id": None}
    )
    assert evaluate_outcome_impact(
        trigger=trigger,
        applicability=not_declared,
        policy=_Policy("policy:b3", "revalidation-required"),
    ).status == "unavailable"


def test_b3_p2a_judgment_module_has_no_persistence_or_mutation_capability() -> None:
    module = importlib.import_module("portable_runtime.governance.outcome_impact_judgment")
    source = inspect.getsource(module)
    tree = ast.parse(source)
    forbidden = {
        "save_record",
        "append_event",
        "commit_event_obligations",
        "commit_verified_outcome",
        "transaction",
        "DistinctionGovernancePersistence",
        "GovernedApplication",
        "GovernanceDecision",
    }
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert forbidden.isdisjoint(referenced)
