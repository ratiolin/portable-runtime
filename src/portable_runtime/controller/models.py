from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.controller.closure import CognitiveClosure
from portable_runtime.controller.revision import RevisionAssessment
from portable_runtime.core.models import new_id, utcnow


class ControllerStatus(StrEnum):
    OPEN = "open"
    WAITING = "waiting"
    CLOSED = "closed"
    REOPEN_REQUIRED = "reopen-required"


class ControllerDecisionKind(StrEnum):
    INVOKE_CAPABILITY = "invoke-capability"
    FORM_CLOSURE = "form-closure"
    PROPOSE_WORK = "propose-work"
    ASSESS_REVISION = "assess-revision"
    CLOSE = "close"
    REOPEN = "reopen"
    WAIT = "wait"


class ControllerState(BaseModel):
    """Minimal durable state for cognitive control.

    The state intentionally references existing runtime/record objects instead
    of defining a second evidence, knowledge, outcome or responsibility plane.
    Closure and revision identities are coordination references, not truth or
    authority stores.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("controller"))
    responsibility_ref: str | None = None
    subject_ref: str | None = None
    context_refs: list[str] = Field(default_factory=list)
    candidate_refs: list[str] = Field(default_factory=list)
    open_issue_refs: list[str] = Field(default_factory=list)
    status: ControllerStatus = ControllerStatus.OPEN
    version: int = 0
    pending_ref: str | None = None
    active_closure_ref: str | None = None
    work_proposal_ref: str | None = None
    last_revision_ref: str | None = None
    last_decision_ref: str | None = None
    last_result_ref: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _valid_state(self) -> ControllerState:
        if self.version < 0:
            raise ValueError("controller state version cannot be negative")
        if self.status is ControllerStatus.WAITING and not self.pending_ref:
            raise ValueError("waiting controller state requires pending_ref")
        if self.status is not ControllerStatus.WAITING and self.pending_ref is not None:
            raise ValueError("only waiting controller state may carry pending_ref")
        return self


class ControllerDecision(BaseModel):
    """A controller selection, not raw reasoner output or execution authority."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("controller_decision"))
    controller_ref: str
    state_version: int
    kind: ControllerDecisionKind
    reason: str = ""
    policy_ref: str | None = None

    # INVOKE_CAPABILITY payload.
    capability: str | None = None
    instruction: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)

    # FORM_CLOSURE payload.
    closure: CognitiveClosure | None = None

    # PROPOSE_WORK payload. The existing persistent-responsibility kernel owns
    # proposal qualification and later Work admission.
    closure_ref: str | None = None
    assessment_ref: str | None = None
    work_kind: str = "generic-task"
    work_title: str | None = None
    work_description: str = ""
    requested_capabilities: list[str] = Field(default_factory=list)
    expected_result: str = ""
    stop_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    effect_class: str = "read-only"

    # ASSESS_REVISION payload.
    revision: RevisionAssessment | None = None

    @model_validator(mode="after")
    def _kind_payload(self) -> ControllerDecision:
        if self.state_version < 0:
            raise ValueError("controller decision state_version cannot be negative")
        if self.policy_ref is not None and not self.policy_ref.strip():
            raise ValueError("controller decision policy_ref cannot be blank")
        if self.kind is ControllerDecisionKind.INVOKE_CAPABILITY:
            if not self.capability or not self.capability.strip():
                raise ValueError("invoke-capability requires capability")
        if self.kind is ControllerDecisionKind.FORM_CLOSURE:
            if self.closure is None:
                raise ValueError("form-closure requires closure")
            if self.closure.controller_ref != self.controller_ref:
                raise ValueError("closure belongs to another controller")
            if self.closure.controller_state_version != self.state_version:
                raise ValueError("closure is not bound to decision state_version")
        if self.kind is ControllerDecisionKind.PROPOSE_WORK:
            if not self.closure_ref or not self.closure_ref.strip():
                raise ValueError("propose-work requires closure_ref")
            if not self.assessment_ref or not self.assessment_ref.strip():
                raise ValueError("propose-work requires assessment_ref")
            if not self.work_title or not self.work_title.strip():
                raise ValueError("propose-work requires work_title")
            if self.effect_class not in {"read-only", "internal-reversible", "external-effect"}:
                raise ValueError("invalid work proposal effect_class")
        if self.kind is ControllerDecisionKind.ASSESS_REVISION:
            if self.revision is None:
                raise ValueError("assess-revision requires revision")
            if self.revision.controller_ref != self.controller_ref:
                raise ValueError("revision belongs to another controller")
            if self.revision.controller_state_version != self.state_version:
                raise ValueError("revision is not bound to decision state_version")
        return self
