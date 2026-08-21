"""Revalidation engine V1.3 — typed dependency + AffectedAssessment.

Implements direct matching per typed edges, no recursive full-graph invalidation.
Supports change_type in {evaluator, model, code, dataset, permission, classification, state_space, environment}
and required_action in {none, warn, background-revalidate, block-next-use, require-human-review, reopen}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import new_id

ChangeType = Literal["evaluator", "model", "code", "dataset", "permission", "classification", "state_space", "environment"]
ImpactType = Literal["none", "warn", "background-revalidate", "block-next-use", "require-human-review", "reopen"]
Severity = Literal["low", "medium", "high", "critical"]
Urgency = Literal["routine", "elevated", "urgent", "immediate"]
BlastRadius = Literal["local", "bounded", "wide", "systemic"]

REQUIRED_ACTIONS: set[str] = {"none", "warn", "background-revalidate", "block-next-use", "require-human-review", "reopen"}
CHANGE_TYPES: set[str] = {"evaluator", "model", "code", "dataset", "permission", "classification", "state_space", "environment"}


class DependencyImpact(BaseModel):
    """Observed dependency impact; it does not prescribe runtime action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_ref: str
    affected_ref: str
    relation_type: str
    impact_type: ImpactType = "warn"
    reason_refs: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Risk interpretation of an observed impact, separate from detection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_ref: str
    affected_ref: str
    severity: Severity = "medium"
    urgency: Urgency = "elevated"
    blast_radius: BlastRadius = "bounded"
    rationale_refs: list[str] = Field(default_factory=list)


class RevalidationDisposition(BaseModel):
    """Policy decision derived from an impact under an explicit profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ImpactType = "warn"
    policy_ref: str = "default-revalidation-policy"
    rationale_refs: list[str] = Field(default_factory=list)


class AffectedAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("affected"))
    change_ref: str
    affected_ref: str
    impact_type: ImpactType = "warn"
    severity: Severity = "medium"
    required_action: ImpactType = "warn"
    reason_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dependency_impact: DependencyImpact | None = None
    risk_assessment: RiskAssessment | None = None
    revalidation_disposition: RevalidationDisposition | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_layers(self) -> AffectedAssessment:
        """Keep legacy flat fields readable while exposing separated layers."""
        if self.dependency_impact is None:
            self.dependency_impact = DependencyImpact(
                change_ref=self.change_ref,
                affected_ref=self.affected_ref,
                relation_type=str(getattr(self, "metadata", {}).get("relation_type", "depends-on")),
                impact_type=self.impact_type,
                reason_refs=list(self.reason_refs),
            )
        else:
            if self.impact_type == "warn" and self.dependency_impact.impact_type != "warn":
                self.impact_type = self.dependency_impact.impact_type
            self.reason_refs = list(self.dependency_impact.reason_refs)
        if self.risk_assessment is None:
            self.risk_assessment = RiskAssessment(
                change_ref=self.change_ref,
                affected_ref=self.affected_ref,
                severity=self.severity,
                rationale_refs=list(self.reason_refs),
            )
        else:
            self.severity = self.risk_assessment.severity
            self.reason_refs = list(self.risk_assessment.rationale_refs or self.reason_refs)
        if self.revalidation_disposition is None:
            self.revalidation_disposition = RevalidationDisposition(
                action=self.required_action,
                rationale_refs=list(self.reason_refs),
            )
        else:
            self.required_action = self.revalidation_disposition.action
        return self


_TYPED_DEPENDENCY_RULES: dict[str, set[str]] = {
    "evaluator": {"validated-under", "evaluated-by"},
    "model": {"validated-under", "evaluated-by", "depends-on"},
    "code": {"executed-with", "validated-under", "depends-on"},
    "dataset": {"measured-by", "depends-on"},
    "permission": {"authorized-under", "depends-on"},
    "classification": {"scoped-to", "depends-on"},
    "state_space": {"scoped-to", "depends-on", "validated-under"},
    "environment": {"validated-under", "executed-with", "measured-by", "depends-on"},
}

_RISK_RULES: dict[str, tuple[Severity, Urgency, BlastRadius]] = {
    "evaluator": ("high", "urgent", "wide"),
    "model": ("high", "urgent", "wide"),
    "code": ("medium", "elevated", "bounded"),
    "dataset": ("medium", "elevated", "bounded"),
    "permission": ("high", "urgent", "wide"),
    "classification": ("medium", "elevated", "bounded"),
    "state_space": ("critical", "immediate", "systemic"),
    "environment": ("high", "urgent", "wide"),
}

_REQUIRED_ACTION_RULES: dict[str, dict[str, ImpactType]] = {
    "evaluator": {"validated-under": "block-next-use", "evaluated-by": "block-next-use", "depends-on": "background-revalidate"},
    "model": {"validated-under": "block-next-use", "evaluated-by": "block-next-use", "depends-on": "background-revalidate"},
    "code": {"executed-with": "block-next-use", "validated-under": "block-next-use", "depends-on": "background-revalidate"},
    "dataset": {"measured-by": "block-next-use", "depends-on": "background-revalidate"},
    "permission": {"authorized-under": "require-human-review", "depends-on": "background-revalidate"},
    "classification": {"scoped-to": "require-human-review", "depends-on": "background-revalidate"},
    "state_space": {"scoped-to": "reopen", "depends-on": "background-revalidate", "validated-under": "block-next-use"},
    "environment": {"validated-under": "block-next-use", "executed-with": "background-revalidate", "measured-by": "background-revalidate", "depends-on": "warn"},
}


def _resolve_required_action(change_type: str, relation_type: str) -> ImpactType:
    per_type = _REQUIRED_ACTION_RULES.get(change_type, {})
    if relation_type in per_type:
        return per_type[relation_type]
    if relation_type in {"validated-under", "evaluated-by"}:
        return "block-next-use"
    if relation_type in {"authorized-under", "scoped-to"}:
        return "require-human-review"
    if relation_type in {"executed-with", "measured-by"}:
        return "background-revalidate"
    return "background-revalidate"


def detect_dependency_impacts(
    change_ref: str,
    change_type: str,
    relations: list[Any],
) -> list[DependencyImpact]:
    """Detect direct typed dependency impacts without selecting an action."""
    if not change_ref:
        raise ValueError("change_ref must be non-empty")
    ct = change_type.strip().lower()
    watch = _TYPED_DEPENDENCY_RULES.get(ct, {"depends-on", "validated-under"})
    affected: list[DependencyImpact] = []
    seen: set[str] = set()
    for rel in relations:
        rt = getattr(rel, "relation_type", None) or getattr(rel, "type", "") or ""
        obj = getattr(rel, "object_ref", None)
        subj = getattr(rel, "subject_ref", None)
        rid = getattr(rel, "id", "")
        if not isinstance(rt, str) or not isinstance(obj, str) or not isinstance(subj, str):
            continue
        if rt not in watch or obj != change_ref or not subj or subj in seen:
            continue
        seen.add(subj)
        affected.append(
            DependencyImpact(
                change_ref=change_ref,
                affected_ref=subj,
                relation_type=rt,
                impact_type="warn",
                reason_refs=[rid] if rid else [],
            )
        )
    return affected


def derive_risk_assessment(
    impact: DependencyImpact,
    *,
    change_type: str,
) -> RiskAssessment:
    """Interpret an observed dependency impact under risk policy."""

    severity, urgency, blast_radius = _RISK_RULES.get(
        change_type.strip().lower(), ("medium", "elevated", "bounded")
    )
    return RiskAssessment(
        change_ref=impact.change_ref,
        affected_ref=impact.affected_ref,
        severity=severity,
        urgency=urgency,
        blast_radius=blast_radius,
        rationale_refs=list(impact.reason_refs),
    )


def derive_revalidation_disposition(
    impact: DependencyImpact,
    *,
    change_type: str,
    policy_ref: str = "default-revalidation-policy",
) -> RevalidationDisposition:
    """Apply an explicit policy profile to one observed impact."""
    action = _resolve_required_action(change_type.strip().lower(), impact.relation_type)
    return RevalidationDisposition(action=action, policy_ref=policy_ref, rationale_refs=list(impact.reason_refs))


def assess_revalidation(
    change_ref: str,
    change_type: str,
    relations: list[Any],
) -> list[AffectedAssessment]:
    """Direct dependency matching — no recursive invalidation.

    Only relations where object_ref == change_ref and relation_type matches
    the typed watch set for change_type are considered affected.
    This prevents full-graph pollution per Plan 7.3.
    """
    if not change_ref:
        raise ValueError("change_ref must be non-empty")
    ct = change_type.strip().lower()
    return [
        AffectedAssessment(
            change_ref=impact.change_ref,
            affected_ref=impact.affected_ref,
            # Flat fields are retained for read compatibility; the explicit
            # impact/risk/disposition objects are authoritative for new callers.
            impact_type=derive_revalidation_disposition(impact, change_type=ct).action,
            severity=derive_risk_assessment(impact, change_type=ct).severity,
            required_action=derive_revalidation_disposition(impact, change_type=ct).action,
            reason_refs=list(impact.reason_refs),
            metadata={"relation_type": impact.relation_type},
            dependency_impact=impact,
            risk_assessment=derive_risk_assessment(impact, change_type=ct),
            revalidation_disposition=derive_revalidation_disposition(impact, change_type=ct),
        )
        for impact in detect_dependency_impacts(change_ref, ct, relations)
    ]


def should_block(affected: AffectedAssessment) -> bool:
    action = affected.revalidation_disposition.action if affected.revalidation_disposition is not None else affected.required_action
    return action in {"block-next-use", "require-human-review", "reopen"}


__all__ = [
    "AffectedAssessment",
    "DependencyImpact",
    "RiskAssessment",
    "RevalidationDisposition",
    "ChangeType",
    "ImpactType",
    "Severity",
    "Urgency",
    "BlastRadius",
    "assess_revalidation",
    "detect_dependency_impacts",
    "derive_revalidation_disposition",
    "derive_risk_assessment",
    "should_block",
    "CHANGE_TYPES",
    "REQUIRED_ACTIONS",
]
