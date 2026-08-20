"""One-class RecordRelation — first-class relations V1.2."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.core.models import new_id

RelationType = Literal[
    "records",
    "supports",
    "contradicts",
    "derived-from",
    "tests",
    "authorizes",
    "produces",
    "revises",
    "supersedes",
    "requires-revalidation",
    "depends-on",
    "validated-under",
    "measured-by",
    "authorized-under",
    "executed-with",
    "evaluated-by",
    "scoped-to",
]

_STABLE_RELATIONS = {
    "records",
    "supports",
    "contradicts",
    "derived-from",
    "tests",
    "authorizes",
    "produces",
    "revises",
    "supersedes",
    "requires-revalidation",
}

class RecordRelation(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("relation"))
    relation_type: RelationType
    subject_ref: str
    object_ref: str
    scope: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_stable(self) -> bool:
        return self.relation_type in _STABLE_RELATIONS

# Invariant: produces != causes
# Runtime must never auto-create "causes"; only "produces" is allowed.
ALLOWED_RELATIONS = set(RelationType.__args__) if hasattr(RelationType, "__args__") else _STABLE_RELATIONS

def validate_relation(rel: RecordRelation) -> list[str]:
    errors = []
    if not rel.subject_ref or not rel.object_ref:
        errors.append("subject_ref and object_ref required")
    if rel.relation_type == "causes":
        errors.append("causes relation must be created by domain attribution, not Runtime (produces != causes)")
    if rel.relation_type not in ALLOWED_RELATIONS and rel.relation_type != "causes":
        # still allow typed dependency edges beyond stable set
        pass
    return errors
