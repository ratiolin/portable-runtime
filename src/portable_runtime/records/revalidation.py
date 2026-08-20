"""Revalidation engine V1.3 — typed dependency + AffectedAssessment.

Implements direct matching per typed edges, no recursive full-graph invalidation.
Supports change_type in {evaluator, model, code, dataset, permission, classification, state_space, environment}
and required_action in {none, warn, background-revalidate, block-next-use, require-human-review, reopen}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.core.models import new_id

ChangeType = Literal["evaluator", "model", "code", "dataset", "permission", "classification", "state_space", "environment"]
ImpactType = Literal["none", "warn", "background-revalidate", "block-next-use", "require-human-review", "reopen"]
Severity = Literal["low", "medium", "high", "critical"]

REQUIRED_ACTIONS: set[str] = {"none", "warn", "background-revalidate", "block-next-use", "require-human-review", "reopen"}
CHANGE_TYPES: set[str] = {"evaluator", "model", "code", "dataset", "permission", "classification", "state_space", "environment"}


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

_SEVERITY_RULES: dict[str, Severity] = {
    "evaluator": "high",
    "model": "high",
    "code": "medium",
    "dataset": "medium",
    "permission": "high",
    "classification": "medium",
    "state_space": "critical",
    "environment": "high",
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
    # normalize change_type
    ct = change_type.strip().lower()
    # allow unknown types but fallback to generic depends-on handling
    watch = _TYPED_DEPENDENCY_RULES.get(ct, {"depends-on", "validated-under"})
    severity: Severity = _SEVERITY_RULES.get(ct, "medium")  # type: ignore[assignment]

    affected: list[AffectedAssessment] = []
    seen: set[str] = set()
    for rel in relations:
        rt = getattr(rel, "relation_type", None) or getattr(rel, "type", "") or ""
        obj = getattr(rel, "object_ref", None)
        subj = getattr(rel, "subject_ref", None)
        rid = getattr(rel, "id", "")
        if not isinstance(rt, str) or not isinstance(obj, str) or not isinstance(subj, str):
            continue
        if rt not in watch:
            continue
        if obj != change_ref:
            continue
        if not subj:
            continue
        if subj in seen:
            continue
        seen.add(subj)
        required: ImpactType = _resolve_required_action(ct, rt)
        # impact_type mirrors required_action for now; spec allows separate but keep consistent
        affected.append(
            AffectedAssessment(
                change_ref=change_ref,
                affected_ref=subj,
                impact_type=required,
                severity=severity,
                required_action=required,
                reason_refs=[rid] if rid else [],
            )
        )
    return affected


def should_block(affected: AffectedAssessment) -> bool:
    return affected.required_action in {"block-next-use", "require-human-review", "reopen"}


__all__ = [
    "AffectedAssessment",
    "ChangeType",
    "ImpactType",
    "Severity",
    "assess_revalidation",
    "should_block",
    "CHANGE_TYPES",
    "REQUIRED_ACTIONS",
]
