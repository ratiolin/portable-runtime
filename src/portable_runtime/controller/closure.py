from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.controller.handoff import CognitiveHandoffEnvelope
from portable_runtime.core.models import new_id, utcnow
from portable_runtime.responsibility.models import EffectClass


class CognitiveClosure(BaseModel):
    """A temporary cognitive closure eligible to hand off into WorkProposal.

    Closure records why exploration is paused for one bounded scope. They do not
    admit Work, authorize effects, verify outcomes or discharge responsibility.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("closure"))
    controller_ref: str
    controller_state_version: int
    responsibility_ref: str | None = None
    subject_ref: str | None = None
    problem_ref: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)

    basis_refs: list[str] = Field(default_factory=list)
    selected_candidate_refs: list[str] = Field(default_factory=list)
    deferred_candidate_refs: list[str] = Field(default_factory=list)
    rejected_candidate_refs: list[str] = Field(default_factory=list)
    deferred_issue_refs: list[str] = Field(default_factory=list)

    selected_direction: str
    rationale: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_plan: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    reopen_conditions: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)
    effect_class: EffectClass = EffectClass.READ_ONLY

    policy_ref: str | None = None
    handoff: CognitiveHandoffEnvelope = Field(default_factory=CognitiveHandoffEnvelope)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _structurally_closed(self) -> CognitiveClosure:
        if self.controller_state_version < 0:
            raise ValueError("closure controller_state_version cannot be negative")
        if not self.selected_direction.strip():
            raise ValueError("closure requires selected_direction")
        if not self.basis_refs:
            raise ValueError("closure requires at least one basis_ref")
        if not self.acceptance_criteria:
            raise ValueError("closure requires acceptance_criteria")
        if not self.verification_plan:
            raise ValueError("closure requires a verification_plan")
        if not self.reopen_conditions:
            raise ValueError("closure requires reopen_conditions")
        return self
