"""Reopen — V1.5 first-class reopen semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import Work, new_id

RevisionScope = Literal[
    "execution",
    "decision",
    "representation",
    "inputs",
    "goal",
    "authorization",
    "evidence-acquisition",
    "verification",
    "problem-definition",
    "other",
]

HandoffDisposition = Literal["carry-forward", "reconsider", "invalidated", "unresolved", "context-only"]
_DEEP_REOPEN_SCOPES = {"representation", "goal", "problem-definition"}


class HandoffEnvelope(BaseModel):
    """Explicit responsibility handoff for a reopened work item."""

    model_config = ConfigDict(extra="allow")

    subject_refs: list[str] = Field(default_factory=list)
    goal_refs: list[str] = Field(default_factory=list)
    constraint_refs: list[str] = Field(default_factory=list)
    assumption_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    observation_refs: list[str] = Field(default_factory=list)
    current_assertion_refs: list[str] = Field(default_factory=list)
    unknown_refs: list[str] = Field(default_factory=list)
    counterevidence_refs: list[str] = Field(default_factory=list)
    still_qualified_candidate_refs: list[str] = Field(default_factory=list)
    authorization_refs: list[str] = Field(default_factory=list)
    closure_refs: list[str] = Field(default_factory=list)
    invalidation_refs: list[str] = Field(default_factory=list)
    reopen_condition_refs: list[str] = Field(default_factory=list)
    dispositions: dict[str, HandoffDisposition] = Field(default_factory=dict)


class ReopenPackage(BaseModel):
    """Portable package carrying old responsibility structure into reopen."""

    model_config = ConfigDict(extra="allow")

    original_work_ref: str
    target_record_ref: str
    current_conclusion_refs: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    counterevidence_refs: list[str] = Field(default_factory=list)
    unknown_scopes: list[str] = Field(default_factory=list)
    still_qualified_candidate_refs: list[str] = Field(default_factory=list)
    rejected_candidate_refs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    reopen_reason: str = ""
    revision_scope: RevisionScope = "other"
    environment_versions: dict[str, str] = Field(default_factory=dict)
    authorization_context: dict[str, Any] = Field(default_factory=dict)
    failure_history_refs: list[str] = Field(default_factory=list)
    handoff: HandoffEnvelope = Field(default_factory=HandoffEnvelope)

class ReopenAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("reopen"))
    record_ref: str = ""
    # ``target_ref`` is retained as a read-compatible spelling used by older
    # callers; canonical code uses record_ref.
    target_ref: str | None = None
    revision_scope: RevisionScope = "other"
    reason: str = ""
    reason_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    package: ReopenPackage | None = None
    handoff: HandoffEnvelope | None = None

    @model_validator(mode="after")
    def _sync_target(self) -> ReopenAssessment:
        if not self.record_ref and self.target_ref:
            self.record_ref = self.target_ref
        if not self.target_ref and self.record_ref:
            self.target_ref = self.record_ref
        return self


def build_reopen_package(
    assessment: ReopenAssessment,
    original_work: Work,
    *,
    handoff: HandoffEnvelope | None = None,
) -> ReopenPackage:
    """Build an explicit handoff package from the original Work and assessment."""
    metadata = original_work.metadata if isinstance(original_work.metadata, dict) else {}
    envelope = handoff or assessment.handoff or HandoffEnvelope(
        subject_refs=[original_work.id],
        assumption_refs=list(metadata.get("assumptions") or []),
        evidence_refs=list(metadata.get("evidence_refs") or []),
        unknown_refs=list(metadata.get("unknown_refs") or []),
        authorization_refs=list(metadata.get("authorization_refs") or metadata.get("authorization_grant_ids") or []),
        reopen_condition_refs=list(metadata.get("reopen_conditions") or []),
    )
    return ReopenPackage(
        original_work_ref=original_work.id,
        target_record_ref=assessment.record_ref or original_work.id,
        current_conclusion_refs=list(metadata.get("current_conclusion_refs") or []),
        scope=dict(metadata.get("valid_scope") or metadata.get("scope") or {}),
        assumptions=list(metadata.get("assumptions") or []),
        evidence_refs=list(metadata.get("evidence_refs") or []),
        counterevidence_refs=list(metadata.get("counterevidence_refs") or []),
        unknown_scopes=list(metadata.get("unknown_scopes") or []),
        still_qualified_candidate_refs=list(metadata.get("still_qualified_candidate_refs") or []),
        rejected_candidate_refs=list(metadata.get("rejected_candidate_refs") or []),
        acceptance_criteria=list(original_work.acceptance_criteria),
        constraints=dict(original_work.constraints),
        inputs=list(original_work.inputs),
        artifact_refs=list(original_work.artifact_refs),
        reopen_reason=assessment.reason,
        revision_scope=assessment.revision_scope,
        environment_versions=dict(metadata.get("environment_versions") or {}),
        authorization_context=dict(metadata.get("authorization_context") or {}),
        failure_history_refs=list(metadata.get("failure_history_refs") or []),
        handoff=envelope,
    )

def create_reopen_work(assessment: ReopenAssessment, original_work: Work) -> Work:
    """Create superseding Work for reopen; preserves old history via supersedes relation."""
    package = assessment.package or build_reopen_package(assessment, original_work)
    deep = assessment.revision_scope in _DEEP_REOPEN_SCOPES
    # Deep reopen changes the problem frame.  It must not resolve to the old
    # workflow, so route it to a neutral reframing work kind and mark the
    # original workflow as explicitly non-rerunnable.
    kind = "reframing" if deep else original_work.kind
    return Work(
        id=new_id("work"),
        title=f"Reopen: {original_work.title}",
        description=assessment.reason,
        kind=kind,
        inputs=list(package.inputs),
        artifact_refs=list(package.artifact_refs),
        constraints=dict(package.constraints),
        acceptance_criteria=list(package.acceptance_criteria),
        metadata={
            "reopen_assessment_id": assessment.id,
            "revision_scope": assessment.revision_scope,
            "supersedes_work_id": original_work.id,
            "reopen_package": package.model_dump(mode="json"),
            "handoff_envelope": package.handoff.model_dump(mode="json"),
            "auto_rerun_original_work": False,
            "deep_reopen": deep,
        },
        parent_work_id=original_work.id,
    )

def should_reopen(assessment: ReopenAssessment) -> bool:
    return bool(assessment.record_ref and assessment.revision_scope != "other")
