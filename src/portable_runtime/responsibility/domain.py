from __future__ import annotations

from datetime import datetime

from portable_runtime.responsibility.models import (
    ResponsibilityAssessment,
    ResponsibilityStatus,
)
from portable_runtime.responsibility.service import ResponsibilityKernel


def record_domain_assessment(
    kernel: ResponsibilityKernel,
    assessment: ResponsibilityAssessment,
    *,
    now: datetime,
) -> ResponsibilityAssessment:
    """Admit an assessment created from a domain-owned fact boundary.

    The domain owns the evidence interpretation that produced the assessment;
    the portable kernel checks only responsibility identity, version, activity
    and freshness. Recording an assessment neither creates Work nor authority.
    """

    version, _statement, _scope = kernel.current_definition(assessment.responsibility_ref)
    if kernel.current_status(assessment.responsibility_ref) is not ResponsibilityStatus.ACTIVE:
        raise ValueError("domain assessment requires an active standing responsibility")
    if assessment.responsibility_version != version:
        raise ValueError("domain assessment is bound to a stale responsibility version")
    if assessment.fresh_until is not None and now > assessment.fresh_until:
        raise ValueError("domain assessment is already stale")
    existing = kernel.journal.get(assessment.id)
    if existing is not None:
        if existing == assessment:
            return assessment
        raise ValueError(f"assessment identity rebound: {assessment.id}")
    kernel.journal.save(assessment)
    return assessment


def due_expectations(
    kernel: ResponsibilityKernel,
    *,
    now: datetime,
) -> list[str]:
    """Return durable expectation ids that need a scheduler wakeup.

    This is a read-only scheduler projection. A returned id is not an
    Observation, Assessment, Work or authorization.
    """

    due: list[tuple[datetime, str]] = []
    for value in kernel.journal.list("ResponsibilityExpectation"):
        responsibility_ref = getattr(value, "responsibility_ref", None)
        responsibility_version = getattr(value, "responsibility_version", None)
        due_at = getattr(value, "due_at", None)
        if not isinstance(responsibility_ref, str) or not isinstance(responsibility_version, int):
            continue
        if not isinstance(due_at, datetime) or due_at > now:
            continue
        try:
            current_version, _statement, _scope = kernel.current_definition(responsibility_ref)
            current_status = kernel.current_status(responsibility_ref)
        except ValueError:
            continue
        if current_status is not ResponsibilityStatus.ACTIVE:
            continue
        if responsibility_version != current_version:
            continue
        if not kernel.expectation_open(value.id):
            continue
        due.append((due_at, value.id))
    return [value_id for _due_at, value_id in sorted(due)]


__all__ = ["due_expectations", "record_domain_assessment"]
