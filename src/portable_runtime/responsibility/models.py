from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import new_id, utcnow


class ResponsibilityStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISCHARGED = "discharged"


class EffectClass(StrEnum):
    READ_ONLY = "read-only"
    INTERNAL_REVERSIBLE = "internal-reversible"
    EXTERNAL_EFFECT = "external-effect"


class ReservationReleaseKind(StrEnum):
    RELEASED = "released"
    EXPIRED = "expired"
    PREEMPTED = "preempted"


class ExpectationResolutionKind(StrEnum):
    SATISFIED = "satisfied"
    CANCELLED = "cancelled"


class ResponsibilityObject(BaseModel):
    """Base class for durable persistent-responsibility state.

    Responsibility objects are durable coordination facts. None is an
    AuthorizationGrant, InvocationPermit, provider execution result or Outcome.
    Objects are append-only; lifecycle is represented by explicit transition
    objects rather than by mutating an identity object in place.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("resp"))
    object_type: str
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _non_empty_id(self) -> ResponsibilityObject:
        if not self.id.strip():
            raise ValueError("responsibility object id must not be empty")
        return self


class StandingResponsibility(ResponsibilityObject):
    object_type: Literal["StandingResponsibility"] = "StandingResponsibility"
    responsibility_kind: str
    statement: str
    scope: dict[str, str] = Field(default_factory=dict)
    schema_version: str = "persistent-responsibility-v1"

    @model_validator(mode="after")
    def _identity_not_empty(self) -> StandingResponsibility:
        if not self.responsibility_kind.strip():
            raise ValueError("responsibility_kind must not be empty")
        if not self.statement.strip():
            raise ValueError("standing responsibility statement must not be empty")
        return self


class ResponsibilityAdmission(ResponsibilityObject):
    object_type: Literal["ResponsibilityAdmission"] = "ResponsibilityAdmission"
    responsibility_ref: str
    responsibility_version: int = 1
    principal_ref: str
    basis_refs: list[str] = Field(default_factory=list)
    admitted_at: datetime = Field(default_factory=utcnow)


class ResponsibilityRevision(ResponsibilityObject):
    object_type: Literal["ResponsibilityRevision"] = "ResponsibilityRevision"
    responsibility_ref: str
    from_version: int
    to_version: int
    statement: str
    scope: dict[str, str] = Field(default_factory=dict)
    basis_refs: list[str] = Field(default_factory=list)
    reason: str = ""

    @model_validator(mode="after")
    def _monotonic(self) -> ResponsibilityRevision:
        if self.to_version != self.from_version + 1:
            raise ValueError("responsibility revision must advance version by exactly one")
        if not self.statement.strip():
            raise ValueError("revised responsibility statement must not be empty")
        return self


class ResponsibilityLifecycleTransition(ResponsibilityObject):
    object_type: Literal["ResponsibilityLifecycleTransition"] = "ResponsibilityLifecycleTransition"
    responsibility_ref: str
    responsibility_version: int
    from_status: ResponsibilityStatus
    to_status: ResponsibilityStatus
    basis_refs: list[str] = Field(default_factory=list)
    decision_ref: str | None = None
    authority_ref: str | None = None
    applied_at: datetime = Field(default_factory=utcnow)
    reason: str = ""

    @model_validator(mode="after")
    def _meaningful_transition(self) -> ResponsibilityLifecycleTransition:
        if self.from_status == self.to_status:
            raise ValueError("responsibility lifecycle transition must change status")
        if self.to_status is ResponsibilityStatus.DISCHARGED and not self.decision_ref:
            raise ValueError("responsibility discharge requires an explicit decision_ref")
        if (
            self.from_status is ResponsibilityStatus.DISCHARGED
            and self.to_status is ResponsibilityStatus.ACTIVE
            and not self.decision_ref
        ):
            raise ValueError("reopening a discharged responsibility requires decision_ref")
        return self


class ResponsibilityExpectation(ResponsibilityObject):
    object_type: Literal["ResponsibilityExpectation"] = "ResponsibilityExpectation"
    responsibility_ref: str
    responsibility_version: int
    subject_ref: str
    expected_signal_kind: str
    due_at: datetime
    recurrence_seconds: int | None = None
    freshness_window_seconds: int | None = None
    source_requirement: str | None = None

    @model_validator(mode="after")
    def _valid_windows(self) -> ResponsibilityExpectation:
        if self.recurrence_seconds is not None and self.recurrence_seconds <= 0:
            raise ValueError("recurrence_seconds must be positive")
        if self.freshness_window_seconds is not None and self.freshness_window_seconds <= 0:
            raise ValueError("freshness_window_seconds must be positive")
        return self


class ResponsibilityExpectationResolution(ResponsibilityObject):
    object_type: Literal["ResponsibilityExpectationResolution"] = "ResponsibilityExpectationResolution"
    expectation_ref: str
    responsibility_ref: str
    resolution: ExpectationResolutionKind
    basis_refs: list[str] = Field(default_factory=list)
    resolved_at: datetime = Field(default_factory=utcnow)


class ResponsibilityAssessment(ResponsibilityObject):
    object_type: Literal["ResponsibilityAssessment"] = "ResponsibilityAssessment"
    responsibility_ref: str
    responsibility_version: int
    subject_ref: str
    assessment_kind: str
    basis_refs: list[str] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utcnow)
    fresh_until: datetime | None = None
    rationale: str = ""


class ResourceVector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    compute_units: int = 0
    api_calls: int = 0
    money_minor: int = 0
    human_attention_units: int = 0
    concurrency_slots: int = 0
    domain_quota: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _non_negative(self) -> ResourceVector:
        base = (
            self.compute_units,
            self.api_calls,
            self.money_minor,
            self.human_attention_units,
            self.concurrency_slots,
        )
        if any(value < 0 for value in base) or any(value < 0 for value in self.domain_quota.values()):
            raise ValueError("resource values cannot be negative")
        return self

    def fits_within(self, other: ResourceVector) -> bool:
        if (
            self.compute_units > other.compute_units
            or self.api_calls > other.api_calls
            or self.money_minor > other.money_minor
            or self.human_attention_units > other.human_attention_units
            or self.concurrency_slots > other.concurrency_slots
        ):
            return False
        return all(value <= other.domain_quota.get(key, 0) for key, value in self.domain_quota.items())

    def plus(self, other: ResourceVector) -> ResourceVector:
        keys = set(self.domain_quota) | set(other.domain_quota)
        return ResourceVector(
            compute_units=self.compute_units + other.compute_units,
            api_calls=self.api_calls + other.api_calls,
            money_minor=self.money_minor + other.money_minor,
            human_attention_units=self.human_attention_units + other.human_attention_units,
            concurrency_slots=self.concurrency_slots + other.concurrency_slots,
            domain_quota={key: self.domain_quota.get(key, 0) + other.domain_quota.get(key, 0) for key in keys},
        )


class PriorityDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urgency: int
    impact: int
    risk: int
    reversibility: int
    confidence: int
    resource_cost: int
    human_attention_cost: int

    @model_validator(mode="after")
    def _bounded(self) -> PriorityDimensions:
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
        return self


class WorkProposal(ResponsibilityObject):
    object_type: Literal["WorkProposal"] = "WorkProposal"
    responsibility_ref: str
    responsibility_version: int
    assessment_ref: str
    subject_ref: str
    work_kind: str
    title: str
    description: str = ""
    requested_resources: ResourceVector = Field(default_factory=ResourceVector)
    requested_capabilities: list[str] = Field(default_factory=list)
    expected_result: str = ""
    stop_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    effect_class: EffectClass = EffectClass.READ_ONLY
    fresh_until: datetime | None = None


class PriorityJudgment(ResponsibilityObject):
    object_type: Literal["PriorityJudgment"] = "PriorityJudgment"
    proposal_ref: str
    dimensions: PriorityDimensions
    policy_ref: str
    admitted: bool
    rationale: str = ""


class ResourcePool(ResponsibilityObject):
    object_type: Literal["ResourcePool"] = "ResourcePool"
    pool_key: str
    capacity: ResourceVector
    policy_ref: str


class PortfolioAdmissionDecision(ResponsibilityObject):
    object_type: Literal["PortfolioAdmissionDecision"] = "PortfolioAdmissionDecision"
    proposal_ref: str
    resource_pool_ref: str
    policy_ref: str
    admitted: bool
    rationale: str = ""


class ResourceReservation(ResponsibilityObject):
    object_type: Literal["ResourceReservation"] = "ResourceReservation"
    responsibility_ref: str
    proposal_ref: str
    resource_pool_ref: str
    resources: ResourceVector
    reserved_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None


class ResourceReservationRelease(ResponsibilityObject):
    object_type: Literal["ResourceReservationRelease"] = "ResourceReservationRelease"
    reservation_ref: str
    responsibility_ref: str
    release_kind: ReservationReleaseKind
    released_at: datetime = Field(default_factory=utcnow)
    reason: str = ""


class Commitment(ResponsibilityObject):
    object_type: Literal["Commitment"] = "Commitment"
    responsibility_ref: str
    responsibility_version: int
    proposal_ref: str
    priority_judgment_ref: str
    portfolio_admission_ref: str
    reservation_ref: str
    resources: ResourceVector
    committed_at: datetime = Field(default_factory=utcnow)
    stop_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)


class ReasoningSessionBinding(ResponsibilityObject):
    object_type: Literal["ReasoningSessionBinding"] = "ReasoningSessionBinding"
    responsibility_ref: str
    responsibility_version: int
    provider: str
    model: str
    session_ref: str
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


class ResponsibilityContextSnapshot(ResponsibilityObject):
    object_type: Literal["ResponsibilityContextSnapshot"] = "ResponsibilityContextSnapshot"
    responsibility_ref: str
    responsibility_version: int
    scope: dict[str, str] = Field(default_factory=dict)
    open_expectation_refs: list[str] = Field(default_factory=list)
    open_assessment_refs: list[str] = Field(default_factory=list)
    unresolved_unknowns: list[str] = Field(default_factory=list)
    active_proposal_refs: list[str] = Field(default_factory=list)
    commitment_refs: list[str] = Field(default_factory=list)
    work_refs: list[str] = Field(default_factory=list)
    reservation_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    qualification_dependency_refs: list[str] = Field(default_factory=list)
    reopen_conditions: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)


class ResponsibilityHandoff(ResponsibilityObject):
    object_type: Literal["ResponsibilityHandoff"] = "ResponsibilityHandoff"
    responsibility_ref: str
    responsibility_version: int
    from_session_ref: str
    to_session_ref: str
    context_snapshot_ref: str
    handed_off_at: datetime = Field(default_factory=utcnow)


class ContinuityValidation(ResponsibilityObject):
    object_type: Literal["ContinuityValidation"] = "ContinuityValidation"
    responsibility_ref: str
    responsibility_version: int
    handoff_ref: str
    responsibility_active: bool
    scope_current: bool
    assessment_current: bool
    expectations_current: bool
    proposals_current: bool
    reservations_current: bool
    authorization_revalidation_required: bool = True
    validated_at: datetime = Field(default_factory=utcnow)
    rationale: str = ""

    @property
    def continuity_ok(self) -> bool:
        return all(
            (
                self.responsibility_active,
                self.scope_current,
                self.assessment_current,
                self.expectations_current,
                self.proposals_current,
                self.reservations_current,
            )
        )


type ResponsibilityValue = Annotated[
    StandingResponsibility
    | ResponsibilityAdmission
    | ResponsibilityRevision
    | ResponsibilityLifecycleTransition
    | ResponsibilityExpectation
    | ResponsibilityExpectationResolution
    | ResponsibilityAssessment
    | WorkProposal
    | PriorityJudgment
    | ResourcePool
    | PortfolioAdmissionDecision
    | ResourceReservation
    | ResourceReservationRelease
    | Commitment
    | ReasoningSessionBinding
    | ResponsibilityContextSnapshot
    | ResponsibilityHandoff
    | ContinuityValidation,
    Field(discriminator="object_type"),
]

_RESPONSIBILITY_MODELS: dict[str, type[ResponsibilityObject]] = {
    str(model.model_fields["object_type"].default): model
    for model in (
        StandingResponsibility,
        ResponsibilityAdmission,
        ResponsibilityRevision,
        ResponsibilityLifecycleTransition,
        ResponsibilityExpectation,
        ResponsibilityExpectationResolution,
        ResponsibilityAssessment,
        WorkProposal,
        PriorityJudgment,
        ResourcePool,
        PortfolioAdmissionDecision,
        ResourceReservation,
        ResourceReservationRelease,
        Commitment,
        ReasoningSessionBinding,
        ResponsibilityContextSnapshot,
        ResponsibilityHandoff,
        ContinuityValidation,
    )
}


def parse_responsibility_object(raw: object) -> ResponsibilityObject:
    if isinstance(raw, ResponsibilityObject):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("responsibility object must be a mapping")
    object_type = raw.get("object_type")
    model = _RESPONSIBILITY_MODELS.get(str(object_type))
    if model is None:
        raise ValueError(f"unknown responsibility object_type: {object_type!r}")
    return model.model_validate(raw)


__all__ = [
    "Commitment",
    "ContinuityValidation",
    "EffectClass",
    "ExpectationResolutionKind",
    "PortfolioAdmissionDecision",
    "PriorityDimensions",
    "PriorityJudgment",
    "ReasoningSessionBinding",
    "ReservationReleaseKind",
    "ResourcePool",
    "ResourceReservation",
    "ResourceReservationRelease",
    "ResourceVector",
    "ResponsibilityAdmission",
    "ResponsibilityAssessment",
    "ResponsibilityContextSnapshot",
    "ResponsibilityExpectation",
    "ResponsibilityExpectationResolution",
    "ResponsibilityHandoff",
    "ResponsibilityLifecycleTransition",
    "ResponsibilityObject",
    "ResponsibilityRevision",
    "ResponsibilityStatus",
    "ResponsibilityValue",
    "StandingResponsibility",
    "WorkProposal",
    "parse_responsibility_object",
]
