from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.controller.handoff import CognitiveHandoffEnvelope
from portable_runtime.core.models import new_id, utcnow


class RevisionScope(StrEnum):
    EXECUTION = "execution"
    WORK_SPEC = "work-spec"
    DECISION = "decision"
    REPRESENTATION = "representation"
    INPUTS = "inputs"
    EVIDENCE_ACQUISITION = "evidence-acquisition"
    VERIFICATION = "verification"
    GOAL = "goal"
    AUTHORIZATION = "authorization"
    PROBLEM_DEFINITION = "problem-definition"


class RevisionDisposition(StrEnum):
    RETRY_RUN = "retry-run"
    REVISE_WORK = "revise-work"
    REOPEN_COGNITION = "reopen-cognition"
    ACQUIRE_EVIDENCE = "acquire-evidence"
    REQUEST_AUTHORIZATION = "request-authorization"
    RECONCILE_EFFECT = "reconcile-effect"
    WAIT = "wait"
    CLOSE = "close"


class RevisionAssessment(BaseModel):
    """A durable diagnosis of what must change after reality returns evidence.

    The assessment does not itself retry a Run, mutate Work, reopen cognition,
    authorize an effect or close a standing responsibility.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("revision"))
    controller_ref: str
    controller_state_version: int
    work_ref: str
    closure_ref: str
    run_ref: str | None = None

    outcome_refs: list[str] = Field(default_factory=list)
    verification_refs: list[str] = Field(default_factory=list)
    reason_refs: list[str] = Field(default_factory=list)
    failure_class: str = ""
    revision_scope: RevisionScope
    recommended_disposition: RevisionDisposition
    reason: str

    carry_forward_refs: list[str] = Field(default_factory=list)
    reconsider_refs: list[str] = Field(default_factory=list)
    invalidated_refs: list[str] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    policy_ref: str | None = None
    handoff: CognitiveHandoffEnvelope = Field(default_factory=CognitiveHandoffEnvelope)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _grounded_revision(self) -> RevisionAssessment:
        if self.controller_state_version < 0:
            raise ValueError("revision controller_state_version cannot be negative")
        if not self.work_ref.strip():
            raise ValueError("revision requires work_ref")
        if not self.closure_ref.strip():
            raise ValueError("revision requires closure_ref")
        if not self.reason.strip():
            raise ValueError("revision requires reason")
        if not (self.outcome_refs or self.verification_refs):
            raise ValueError("revision requires outcome_refs or verification_refs")
        if (
            self.recommended_disposition is RevisionDisposition.CLOSE
            and not self.verification_refs
        ):
            raise ValueError("close disposition requires verification_refs")
        if (
            self.recommended_disposition is RevisionDisposition.RECONCILE_EFFECT
            and self.revision_scope is not RevisionScope.EXECUTION
        ):
            raise ValueError("reconcile-effect requires execution revision_scope")
        if (
            self.recommended_disposition is RevisionDisposition.REQUEST_AUTHORIZATION
            and self.revision_scope is not RevisionScope.AUTHORIZATION
        ):
            raise ValueError("request-authorization requires authorization revision_scope")
        if (
            self.recommended_disposition is RevisionDisposition.RETRY_RUN
            and self.revision_scope
            not in {
                RevisionScope.EXECUTION,
                RevisionScope.WORK_SPEC,
                RevisionScope.DECISION,
            }
        ):
            raise ValueError("retry-run is incompatible with deep revision_scope")
        return self
