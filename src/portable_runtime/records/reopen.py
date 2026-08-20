"""Reopen — V1.5 first-class reopen semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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

class ReopenAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("reopen"))
    record_ref: str
    revision_scope: RevisionScope = "other"
    reason: str = ""
    reason_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)

def create_reopen_work(assessment: ReopenAssessment, original_work: Work) -> Work:
    """Create superseding Work for reopen; preserves old history via supersedes relation."""
    return Work(
        id=new_id("work"),
        title=f"Reopen: {original_work.title}",
        description=assessment.reason,
        kind=original_work.kind,
        metadata={
            "reopen_assessment_id": assessment.id,
            "revision_scope": assessment.revision_scope,
            "supersedes_work_id": original_work.id,
        },
        parent_work_id=original_work.id,
    )

def should_reopen(assessment: ReopenAssessment) -> bool:
    return bool(assessment.record_ref and assessment.revision_scope != "other")
