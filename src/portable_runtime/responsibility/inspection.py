from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.responsibility.models import (
    Commitment,
    ReasoningSessionBinding,
    ResourceReservation,
    ResponsibilityAdmission,
    ResponsibilityAssessment,
    ResponsibilityExpectation,
    ResponsibilityHandoff,
    ResponsibilityStatus,
    WorkProposal,
)
from portable_runtime.responsibility.service import ResponsibilityKernel


class ResponsibilityInspection(BaseModel):
    """Read-only, non-authority-bearing operator projection."""

    model_config = ConfigDict(extra="forbid")

    authority_bearing: bool = False
    responsibility_ref: str
    responsibility_version: int
    status: ResponsibilityStatus
    principal_ref: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)
    current_expectation_refs: list[str] = Field(default_factory=list)
    last_assessment_ref: str | None = None
    open_proposal_refs: list[str] = Field(default_factory=list)
    commitment_refs: list[str] = Field(default_factory=list)
    work_refs: list[str] = Field(default_factory=list)
    resource_reservation_refs: list[str] = Field(default_factory=list)
    current_reasoning_session_refs: list[str] = Field(default_factory=list)
    recent_handoff_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    escalation_reasons: list[str] = Field(default_factory=list)


def _created_at(value: Any) -> datetime:
    created_at = getattr(value, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at
    raise ValueError("responsibility object lacks created_at")


def inspect_responsibility(
    kernel: ResponsibilityKernel,
    responsibility_ref: str,
    *,
    now: datetime,
) -> ResponsibilityInspection:
    """Explain durable responsibility state without creating authority or Work."""

    version, _statement, scope = kernel.current_definition(responsibility_ref)
    status = kernel.current_status(responsibility_ref)

    admissions = [
        value
        for value in kernel.journal.list("ResponsibilityAdmission", responsibility_ref)
        if isinstance(value, ResponsibilityAdmission)
    ]
    principal_ref = admissions[0].principal_ref if admissions else None

    expectations = [
        value
        for value in kernel.journal.list("ResponsibilityExpectation", responsibility_ref)
        if isinstance(value, ResponsibilityExpectation)
        and value.responsibility_version == version
        and kernel.expectation_open(value.id)
    ]
    assessments = [
        value
        for value in kernel.journal.list("ResponsibilityAssessment", responsibility_ref)
        if isinstance(value, ResponsibilityAssessment) and value.responsibility_version == version
    ]
    proposals = [
        value
        for value in kernel.journal.list("WorkProposal", responsibility_ref)
        if isinstance(value, WorkProposal) and value.responsibility_version == version
    ]
    commitments = [
        value
        for value in kernel.journal.list("Commitment", responsibility_ref)
        if isinstance(value, Commitment) and value.responsibility_version == version
    ]
    reservations = [
        value
        for value in kernel.journal.list("ResourceReservation", responsibility_ref)
        if isinstance(value, ResourceReservation) and not kernel._reservation_released(value, now=now)
    ]
    sessions = [
        value
        for value in kernel.journal.list("ReasoningSessionBinding", responsibility_ref)
        if isinstance(value, ReasoningSessionBinding)
        and value.responsibility_version == version
        and (value.ended_at is None or value.ended_at > now)
    ]
    handoffs = [
        value
        for value in kernel.journal.list("ResponsibilityHandoff", responsibility_ref)
        if isinstance(value, ResponsibilityHandoff) and value.responsibility_version == version
    ]
    work_refs = [
        work.id
        for work in kernel.store.list_work()
        if isinstance(work.metadata, dict)
        and work.metadata.get("standing_responsibility_ref") == responsibility_ref
    ]

    blocked: list[str] = []
    if status is ResponsibilityStatus.SUSPENDED:
        blocked.append("responsibility-suspended")
    if status is ResponsibilityStatus.DISCHARGED:
        blocked.append("responsibility-discharged")
    if expectations and all(value.due_at > now for value in expectations):
        blocked.append("waiting-for-expectation")
    if proposals and not commitments:
        blocked.append("proposal-awaiting-admission-or-commitment")

    escalation: list[str] = []
    for proposal in proposals:
        escalation.extend(proposal.escalation_conditions)

    last_assessment = max(assessments, key=_created_at) if assessments else None
    return ResponsibilityInspection(
        responsibility_ref=responsibility_ref,
        responsibility_version=version,
        status=status,
        principal_ref=principal_ref,
        scope=scope,
        current_expectation_refs=[value.id for value in expectations],
        last_assessment_ref=last_assessment.id if last_assessment else None,
        open_proposal_refs=[value.id for value in proposals],
        commitment_refs=[value.id for value in commitments],
        work_refs=work_refs,
        resource_reservation_refs=[value.id for value in reservations],
        current_reasoning_session_refs=[value.id for value in sessions],
        recent_handoff_refs=[value.id for value in sorted(handoffs, key=_created_at)[-10:]],
        blocked_reasons=blocked,
        escalation_reasons=list(dict.fromkeys(escalation)),
    )


__all__ = ["ResponsibilityInspection", "inspect_responsibility"]
