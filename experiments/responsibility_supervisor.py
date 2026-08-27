"""Experimental coordinator for persistent responsibility.

The supervisor is deliberately not an AgentLoop. It does not reason about the
world, mint authority, or own external facts. It only enforces the ordering and
resource boundaries between already-separated responsibility positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from experiments.persistent_agency import (
    Commitment,
    EscalationPolicy,
    ExpectedSignal,
    PriorityJudgment,
    ResourceEnvelope,
    ResourceRequest,
    ResponsibilityPortfolio,
    ResponsibilityStatus,
    SituationAssessment,
    StandingResponsibility,
    WorkProposal,
    WorkRecord,
    assess_missing_signal,
)


@dataclass(frozen=True, slots=True)
class ResourceConsumption:
    commitment_ref: str
    consumed: ResourceRequest
    recorded_at: datetime
    evidence_refs: tuple[str, ...] = ()


@dataclass(slots=True)
class ResponsibilitySupervisor:
    """Coordinate responsibility positions without collapsing their authority."""

    portfolio: ResponsibilityPortfolio = field(default_factory=ResponsibilityPortfolio)
    escalation_policy: EscalationPolicy = field(default_factory=EscalationPolicy)
    assessments: dict[str, SituationAssessment] = field(default_factory=dict)
    consumptions: dict[str, list[ResourceConsumption]] = field(default_factory=dict)

    def register_responsibility(self, responsibility: StandingResponsibility) -> None:
        self.portfolio.add_responsibility(responsibility)

    def register_assessment(self, assessment: SituationAssessment) -> None:
        if assessment.id in self.assessments:
            raise ValueError(f"situation assessment already exists: {assessment.id}")
        responsibility = self.portfolio.responsibilities.get(assessment.responsibility_ref)
        if responsibility is None:
            raise ValueError("situation assessment requires a known standing responsibility")
        if responsibility.status is not ResponsibilityStatus.ACTIVE:
            raise ValueError("situation assessment requires an active standing responsibility")
        self.assessments[assessment.id] = assessment

    def register_missing_signal(
        self,
        *,
        responsibility_ref: str,
        expectation: ExpectedSignal,
        now: datetime,
        observed_evidence_refs: tuple[str, ...],
        assessment_id: str,
    ) -> SituationAssessment | None:
        responsibility = self.portfolio.responsibilities.get(responsibility_ref)
        if responsibility is None:
            raise ValueError("missing-signal assessment requires a known responsibility")
        assessment = assess_missing_signal(
            responsibility=responsibility,
            expectation=expectation,
            now=now,
            observed_evidence_refs=observed_evidence_refs,
            assessment_id=assessment_id,
        )
        if assessment is not None:
            self.register_assessment(assessment)
        return assessment

    def register_proposal(self, proposal: WorkProposal) -> None:
        assessment = self.assessments.get(proposal.assessment_ref)
        if assessment is None:
            raise ValueError("work proposal requires a registered situation assessment")
        if assessment.responsibility_ref != proposal.responsibility_ref:
            raise ValueError("proposal and assessment responsibility refs must match")
        self.portfolio.add_proposal(proposal)

    def commit(
        self,
        *,
        commitment: Commitment,
        priority: PriorityJudgment,
        envelope: ResourceEnvelope,
    ) -> None:
        self.portfolio.commit(
            commitment=commitment,
            priority=priority,
            envelope=envelope,
        )

    def start_work(self, work: WorkRecord) -> WorkRecord:
        return self.portfolio.start_work(work)

    def complete_work(self, work_id: str) -> WorkRecord:
        return self.portfolio.complete_work(work_id)

    def record_consumption(self, consumption: ResourceConsumption) -> ResourceRequest:
        commitment = self.portfolio.commitments.get(consumption.commitment_ref)
        if commitment is None:
            raise ValueError("resource consumption requires a known commitment")
        prior = self.consumptions.get(consumption.commitment_ref, [])
        total = _sum_requests([item.consumed for item in prior] + [consumption.consumed])
        if not _request_within(total, commitment.resource_allocation):
            raise ValueError("resource consumption exceeds committed allocation")
        self.consumptions.setdefault(consumption.commitment_ref, []).append(consumption)
        return total


def _sum_requests(requests: list[ResourceRequest]) -> ResourceRequest:
    return ResourceRequest(
        compute_units=sum(item.compute_units for item in requests),
        api_calls=sum(item.api_calls for item in requests),
        money_minor=sum(item.money_minor for item in requests),
        human_attention_units=sum(item.human_attention_units for item in requests),
    )


def _request_within(actual: ResourceRequest, ceiling: ResourceRequest) -> bool:
    return (
        actual.compute_units <= ceiling.compute_units
        and actual.api_calls <= ceiling.api_calls
        and actual.money_minor <= ceiling.money_minor
        and actual.human_attention_units <= ceiling.human_attention_units
    )
