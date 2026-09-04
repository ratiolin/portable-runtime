from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HandoffDisposition(StrEnum):
    CARRY_FORWARD = "carry-forward"
    RECONSIDER = "reconsider"
    INVALIDATED = "invalidated"
    UNRESOLVED = "unresolved"
    CONTEXT_ONLY = "context-only"


class CognitiveHandoffEnvelope(BaseModel):
    """Responsibility-preserving cognitive handoff between open and closed work.

    The envelope is coordination/provenance only. It does not promote any
    referenced material to truth, qualification, Work admission or authority.
    """

    model_config = ConfigDict(extra="forbid")

    subject_refs: list[str] = Field(default_factory=list)
    goal_refs: list[str] = Field(default_factory=list)
    constraint_refs: list[str] = Field(default_factory=list)
    assumption_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    observation_refs: list[str] = Field(default_factory=list)
    assertion_refs: list[str] = Field(default_factory=list)
    unknown_refs: list[str] = Field(default_factory=list)
    counterevidence_refs: list[str] = Field(default_factory=list)
    selected_candidate_refs: list[str] = Field(default_factory=list)
    deferred_candidate_refs: list[str] = Field(default_factory=list)
    rejected_candidate_refs: list[str] = Field(default_factory=list)
    authorization_refs: list[str] = Field(default_factory=list)
    closure_refs: list[str] = Field(default_factory=list)
    invalidation_refs: list[str] = Field(default_factory=list)
    reopen_condition_refs: list[str] = Field(default_factory=list)
    dispositions: dict[str, HandoffDisposition] = Field(default_factory=dict)
