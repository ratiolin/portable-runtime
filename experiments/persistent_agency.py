"""Experimental Stage-4 responsibility coordination.

This module is intentionally outside ``src/portable_runtime`` and the canonical
contract catalog. It is a falsifiable specialization for persistent governed
agency, not a public runtime API.

The central invariant is that a durable Work is not the owner of an enduring
responsibility. A StandingResponsibility can produce many Work proposals over
time, and completing one Work never discharges the standing responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable


class ResponsibilityStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISCHARGED = "discharged"


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    REJECTED = "rejected"
    COMMITTED = "committed"


class WorkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EscalationRoute(StrEnum):
    AUTONOMOUS = "autonomous"
    HUMAN_REVIEW = "human-review"
    PROHIBITED = "prohibited"


@dataclass(frozen=True, slots=True)
class StandingResponsibility:
    id: str
    statement: str
    scope: dict[str, str] = field(default_factory=dict)
    status: ResponsibilityStatus = ResponsibilityStatus.ACTIVE
    authority_bearing: bool = False


@dataclass(frozen=True, slots=True)
class Observation:
    id: str
    subject_ref: str
    observed_at: datetime
    evidence_refs: tuple[str, ...]
    facts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExpectedSignal:
    id: str
    subject_ref: str
    due_at: datetime
    evidence_kind: str


@dataclass(frozen=True, slots=True)
class SituationAssessment:
    id: str
    responsibility_ref: str
    subject_ref: str
    assessment_kind: str
    basis_refs: tuple[str, ...]
    assessed_at: datetime
    rationale: str
    authority_bearing: bool = False


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    compute_units: int = 0
    api_calls: int = 0
    money_minor: int = 0
    human_attention_units: int = 0

    def __post_init__(self) -> None:
        values = (
            self.compute_units,
            self.api_calls,
            self.money_minor,
            self.human_attention_units,
        )
        if any(value < 0 for value in values):
            raise ValueError("resource requests cannot be negative")


@dataclass(frozen=True, slots=True)
class ResourceEnvelope:
    compute_units: int
    api_calls: int
    money_minor: int
    human_attention_units: int

    def __post_init__(self) -> None:
        values = (
            self.compute_units,
            self.api_calls,
            self.money_minor,
            self.human_attention_units,
        )
        if any(value < 0 for value in values):
            raise ValueError("resource envelopes cannot be negative")

    def admits(self, request: ResourceRequest) -> bool:
        return (
            request.compute_units <= self.compute_units
            and request.api_calls <= self.api_calls
            and request.money_minor <= self.money_minor
            and request.human_attention_units <= self.human_attention_units
        )


@dataclass(frozen=True, slots=True)
class PriorityDimensions:
    urgency: int
    impact: int
    risk: int
    reversibility: int
    confidence: int
    resource_cost: int
    human_attention_cost: int

    def __post_init__(self) -> None:
        for value in (
            self.urgency,
            self.impact,
            self.risk,
            self.reversibility,
            self.confidence,
            self.resource_cost,
            self.human_attention_cost,
        ):
            if not 0 <= value <= 5:
                raise ValueError("priority dimensions must be in [0, 5]")


@dataclass(frozen=True, slots=True)
class PriorityJudgment:
    id: str
    proposal_ref: str
    dimensions: PriorityDimensions
    admitted: bool
    rationale: str
    authority_bearing: bool = False


@dataclass(frozen=True, slots=True)
class WorkProposal:
    id: str
    responsibility_ref: str
    assessment_ref: str
    proposed_work_kind: str
    subject_ref: str
    resource_request: ResourceRequest
    stop_conditions: tuple[str, ...]
    escalation_conditions: tuple[str, ...]
    status: ProposalStatus = ProposalStatus.PROPOSED
    authority_bearing: bool = False


@dataclass(frozen=True, slots=True)
class Commitment:
    id: str
    responsibility_ref: str
    proposal_ref: str
    priority_judgment_ref: str
    resource_allocation: ResourceRequest
    stop_conditions: tuple[str, ...]
    escalation_conditions: tuple[str, ...]
    committed_at: datetime
    execution_authorization_ref: str | None = None
    authority_bearing: bool = False


@dataclass(frozen=True, slots=True)
class WorkRecord:
    id: str
    commitment_ref: str
    responsibility_ref: str
    work_kind: str
    subject_ref: str
    status: WorkStatus = WorkStatus.PENDING


@dataclass(frozen=True, slots=True)
class RoleDelegation:
    id: str
    principal_ref: str
    delegate_ref: str
    responsibility_ref: str
    may_subdelegate: bool = False


@dataclass(frozen=True, slots=True)
class EscalationPolicy:
    """Domain policy for deciding whether a proposed action may stay autonomous."""

    financial_effects_require_human: bool = True
    irreversible_effects_require_human: bool = True

    def route(
        self,
        *,
        external_effect: bool,
        financial_effect: bool,
        reversible: bool,
        explicitly_prohibited: bool = False,
    ) -> EscalationRoute:
        if explicitly_prohibited:
            return EscalationRoute.PROHIBITED
        if financial_effect and self.financial_effects_require_human:
            return EscalationRoute.HUMAN_REVIEW
        if external_effect and not reversible and self.irreversible_effects_require_human:
            return EscalationRoute.HUMAN_REVIEW
        return EscalationRoute.AUTONOMOUS


@dataclass(slots=True)
class ResponsibilityPortfolio:
    responsibilities: dict[str, StandingResponsibility] = field(default_factory=dict)
    proposals: dict[str, WorkProposal] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    work: dict[str, WorkRecord] = field(default_factory=dict)

    def add_responsibility(self, responsibility: StandingResponsibility) -> None:
        if responsibility.id in self.responsibilities:
            raise ValueError(f"standing responsibility already exists: {responsibility.id}")
        self.responsibilities[responsibility.id] = responsibility

    def add_proposal(self, proposal: WorkProposal) -> None:
        responsibility = self._responsibility(proposal.responsibility_ref)
        if proposal.id in self.proposals:
            raise ValueError(f"work proposal already exists: {proposal.id}")
        if responsibility.status is not ResponsibilityStatus.ACTIVE:
            raise ValueError("work may only be proposed under an active standing responsibility")
        self.proposals[proposal.id] = proposal

    def commit(
        self,
        *,
        commitment: Commitment,
        priority: PriorityJudgment,
        envelope: ResourceEnvelope,
    ) -> None:
        responsibility = self._responsibility(commitment.responsibility_ref)
        if responsibility.status is not ResponsibilityStatus.ACTIVE:
            raise ValueError("commitment requires an active standing responsibility")
        proposal = self.proposals.get(commitment.proposal_ref)
        if proposal is None:
            raise ValueError("commitment requires an existing work proposal")
        if proposal.responsibility_ref != responsibility.id:
            raise ValueError("proposal and commitment responsibility refs must match")
        if priority.proposal_ref != proposal.id:
            raise ValueError("priority judgment must apply to the committed proposal")
        if priority.id != commitment.priority_judgment_ref:
            raise ValueError("commitment must bind the supplied priority judgment")
        if not priority.admitted:
            raise ValueError("rejected proposal cannot be committed")
        if commitment.resource_allocation != proposal.resource_request:
            raise ValueError("commitment allocation must bind the proposal resource request")
        if not envelope.admits(commitment.resource_allocation):
            raise ValueError("resource allocation exceeds the governing envelope")
        if commitment.id in self.commitments:
            raise ValueError(f"commitment already exists: {commitment.id}")
        self.commitments[commitment.id] = commitment
        self.proposals[proposal.id] = WorkProposal(
            id=proposal.id,
            responsibility_ref=proposal.responsibility_ref,
            assessment_ref=proposal.assessment_ref,
            proposed_work_kind=proposal.proposed_work_kind,
            subject_ref=proposal.subject_ref,
            resource_request=proposal.resource_request,
            stop_conditions=proposal.stop_conditions,
            escalation_conditions=proposal.escalation_conditions,
            status=ProposalStatus.COMMITTED,
            authority_bearing=proposal.authority_bearing,
        )

    def start_work(self, work: WorkRecord) -> WorkRecord:
        commitment = self.commitments.get(work.commitment_ref)
        if commitment is None:
            raise ValueError("work requires an existing commitment")
        if commitment.responsibility_ref != work.responsibility_ref:
            raise ValueError("work and commitment responsibility refs must match")
        responsibility = self._responsibility(work.responsibility_ref)
        if responsibility.status is not ResponsibilityStatus.ACTIVE:
            raise ValueError("work requires an active standing responsibility")
        running = WorkRecord(
            id=work.id,
            commitment_ref=work.commitment_ref,
            responsibility_ref=work.responsibility_ref,
            work_kind=work.work_kind,
            subject_ref=work.subject_ref,
            status=WorkStatus.RUNNING,
        )
        self.work[running.id] = running
        return running

    def complete_work(self, work_id: str) -> WorkRecord:
        existing = self.work.get(work_id)
        if existing is None:
            raise ValueError("unknown work")
        completed = WorkRecord(
            id=existing.id,
            commitment_ref=existing.commitment_ref,
            responsibility_ref=existing.responsibility_ref,
            work_kind=existing.work_kind,
            subject_ref=existing.subject_ref,
            status=WorkStatus.COMPLETED,
        )
        self.work[work_id] = completed
        # Deliberately does not mutate standing responsibility lifecycle.
        return completed

    def discharge_responsibility(self, responsibility_id: str) -> StandingResponsibility:
        current = self.responsibilities.get(responsibility_id)
        if current is None:
            raise ValueError("unknown standing responsibility")
        discharged = StandingResponsibility(
            id=current.id,
            statement=current.statement,
            scope=current.scope,
            status=ResponsibilityStatus.DISCHARGED,
            authority_bearing=current.authority_bearing,
        )
        self.responsibilities[responsibility_id] = discharged
        return discharged

    def _responsibility(self, responsibility_id: str) -> StandingResponsibility:
        responsibility = self.responsibilities.get(responsibility_id)
        if responsibility is None:
            raise ValueError(f"unknown standing responsibility: {responsibility_id}")
        return responsibility


def assess_missing_signal(
    *,
    responsibility: StandingResponsibility,
    expectation: ExpectedSignal,
    now: datetime,
    observed_evidence_refs: Iterable[str],
    assessment_id: str,
) -> SituationAssessment | None:
    """Turn elapsed expectation without evidence into a situation assessment."""

    observed = tuple(str(ref) for ref in observed_evidence_refs if str(ref))
    if observed or now < expectation.due_at:
        return None
    return SituationAssessment(
        id=assessment_id,
        responsibility_ref=responsibility.id,
        subject_ref=expectation.subject_ref,
        assessment_kind="expected-signal-missing",
        basis_refs=(expectation.id,),
        assessed_at=now,
        rationale=f"expected {expectation.evidence_kind} evidence is absent after due_at",
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


CANDIDATE_NON_EQUIVALENCES: tuple[tuple[str, str], ...] = (
    ("Observation", "SituationAssessment"),
    ("SituationAssessment", "WorkProposal"),
    ("WorkProposal", "Commitment"),
    ("Commitment", "ExecutionAuthorization"),
    ("PriorityJudgment", "ValueTruth"),
    ("ResourceAllocation", "ExternalEffectAuthority"),
    ("TaskCompleted", "StandingResponsibilityDischarged"),
    ("StandingResponsibility", "PermanentAuthority"),
    ("RoleDelegation", "SubdelegationRight"),
    ("NoObservedFailure", "ConditionVerifiedHealthy"),
)
