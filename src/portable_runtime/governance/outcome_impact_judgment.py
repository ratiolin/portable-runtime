"""Pure F1-B3 Outcome impact judgment.

This layer interprets an authoritative confirmed Outcome only after explicit
applicability has been established.  It owns no persistence and has no default
mapping from objective pass/fail to governance consequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from portable_runtime.governance.outcome_impact import (
    OutcomeConfirmedTriggerResolution,
    OutcomeGovernanceApplicability,
)
from portable_runtime.records.models import OutcomeRecord

OutcomeImpact = Literal[
    "no-governance-impact",
    "recovery-only",
    "revalidation-required",
    "qualification-challenged",
    "unknown",
]
OutcomeImpactEvaluationStatus = Literal["ready", "unavailable"]


class OutcomeImpactPolicy(Protocol):
    """Explicit policy responsibility for interpreting one applicable Outcome."""

    @property
    def policy_ref(self) -> str: ...

    def judge(
        self,
        outcome: OutcomeRecord,
        applicability: OutcomeGovernanceApplicability,
    ) -> tuple[OutcomeImpact, tuple[str, ...]] | None: ...


@dataclass(frozen=True)
class OutcomeImpactJudgment:
    outcome_ref: str
    trigger_event_ref: str
    action_ref: str
    scheme_id: str
    context: str
    impact: OutcomeImpact
    policy_ref: str
    rationale_refs: tuple[str, ...]
    applicability_basis_refs: tuple[str, ...]


@dataclass(frozen=True)
class OutcomeImpactEvaluation:
    status: OutcomeImpactEvaluationStatus
    impact: OutcomeImpact
    reason: str
    judgment: OutcomeImpactJudgment | None = None


def evaluate_outcome_impact(
    *,
    trigger: OutcomeConfirmedTriggerResolution,
    applicability: OutcomeGovernanceApplicability,
    policy: OutcomeImpactPolicy,
) -> OutcomeImpactEvaluation:
    """Evaluate governance meaning without mutating or persisting anything."""

    outcome = trigger.outcome
    if not trigger.authoritative or trigger.event is None or outcome is None:
        return OutcomeImpactEvaluation("unavailable", "unknown", "authoritative-trigger-unavailable")
    if not applicability.applicable or applicability.scheme_id is None:
        return OutcomeImpactEvaluation("unavailable", "unknown", "applicability-not-established")
    if applicability.outcome_ref != outcome.id or applicability.action_ref != outcome.action_ref:
        return OutcomeImpactEvaluation("unavailable", "unknown", "applicability-trigger-mismatch")
    if not policy.policy_ref.strip():
        return OutcomeImpactEvaluation("unavailable", "unknown", "impact-policy-identity-missing")

    resolved = policy.judge(outcome, applicability)
    if resolved is None:
        return OutcomeImpactEvaluation("unavailable", "unknown", "impact-judgment-unavailable")
    impact, rationale_refs = resolved
    if impact == "unknown":
        return OutcomeImpactEvaluation("unavailable", "unknown", "impact-judgment-unknown")
    refs = tuple(dict.fromkeys(ref.strip() for ref in rationale_refs if ref.strip()))
    if not refs:
        return OutcomeImpactEvaluation("unavailable", "unknown", "impact-rationale-missing")

    judgment = OutcomeImpactJudgment(
        outcome_ref=outcome.id,
        trigger_event_ref=trigger.event.id,
        action_ref=outcome.action_ref,
        scheme_id=applicability.scheme_id,
        context=applicability.context,
        impact=impact,
        policy_ref=policy.policy_ref,
        rationale_refs=refs,
        applicability_basis_refs=applicability.basis_refs,
    )
    return OutcomeImpactEvaluation("ready", impact, "impact-judgment-ready", judgment)


__all__ = [
    "OutcomeImpact",
    "OutcomeImpactEvaluation",
    "OutcomeImpactEvaluationStatus",
    "OutcomeImpactJudgment",
    "OutcomeImpactPolicy",
    "evaluate_outcome_impact",
]
