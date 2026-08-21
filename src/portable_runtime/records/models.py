"""Semantic Plane records — Control Plane record layer V1.2.

Implements 3 orthogonal dimensions:
  record_type ⊥ epistemic_status ⊥ lifecycle_status
and enforces that supported/verified/official/authorized are never conflated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import new_id, utcnow

RecordType = Literal[
    "EvidenceArtifact",
    "Observation",
    "Assertion",
    "Goal",
    "Constraint",
    "Experiment",
    "Decision",
    "Action",
    "Outcome",
    "Revision",
    "ChangeObject",
    "Policy",
    "Derivation",
]

EpistemicStatus = Literal["unverified", "supported", "contested", "refuted", "unknown", "revalidation-required"]

LifecycleStatus = Literal[
    "draft",
    "current",
    "superseded",
    "archived",
    "proposed",
    "authorized",
    "applied",
    "verified",
    "accepted",
    "rejected",
    "rolled-back",
    "candidate",
    "official",
    "deprecated",
    "recorded",
    "confirmed",
]

# Allowed lifecycles per record_type (simplified V1.2)
_ALLOWED_LIFECYCLE: dict[str, set[str]] = {
    "EvidenceArtifact": {"draft", "current", "superseded", "archived"},
    "Observation": {"draft", "current", "superseded", "archived"},
    "Assertion": {"draft", "current", "superseded", "archived"},
    "Goal": {"proposed", "current", "superseded", "archived"},
    "Constraint": {"draft", "current", "superseded", "archived"},
    "Experiment": {"draft", "current", "superseded", "archived"},
    "Decision": {"draft", "current", "superseded", "archived"},
    "Action": {"recorded", "verified", "current", "superseded"},
    "Outcome": {"recorded", "confirmed", "superseded", "archived"},
    "Revision": {"proposed", "authorized", "applied", "verified", "accepted", "rejected", "rolled-back"},
    "ChangeObject": {"draft", "candidate", "official", "deprecated", "archived"},
    "Policy": {"draft", "candidate", "official", "deprecated", "archived"},
    "Derivation": {"draft", "current", "superseded", "archived"},
}

# Which types may carry epistemic_status
_EPISTEMIC_ALLOWED = {"Assertion", "Observation"}

class BaseRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("record"))
    record_type: RecordType
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = "system"
    system_boundary: str = "runtime"
    scope: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    environment_versions: dict[str, str] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    unknown_scopes: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    lifecycle_status: LifecycleStatus = "draft"
    epistemic_status: EpistemicStatus | None = None
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_orthogonal(self) -> BaseRecord:
        # epistemic_status only for proposition-type records
        # Action uses type-specific status, not epistemic
        if self.epistemic_status is not None and self.record_type not in _EPISTEMIC_ALLOWED:
            raise ValueError(
                f"{self.record_type} must not carry epistemic_status, use type-specific status"
            )
        # lifecycle must be allowed for type (warn, not hard fail for extensibility)
        allowed = _ALLOWED_LIFECYCLE.get(self.record_type)
        if allowed and self.lifecycle_status not in allowed:
            raise ValueError(f"lifecycle_status {self.lifecycle_status!r} not allowed for {self.record_type}")
        return self


class EvidenceArtifact(BaseRecord):
    record_type: RecordType = "EvidenceArtifact"
    kind: str = "artifact"
    uri: str | None = None
    media_type: str | None = None
    checksum: str | None = None
    lifecycle_status: LifecycleStatus = "current"


class Observation(BaseRecord):
    record_type: RecordType = "Observation"
    observed_at: datetime = Field(default_factory=utcnow)
    method: str = ""
    location: str = ""
    kind: str = "observation"


class Assertion(BaseRecord):
    record_type: RecordType = "Assertion"
    kind: Literal["claim", "hypothesis", "challenge", "assertion"] = "claim"
    statement: str = ""
    epistemic_status: EpistemicStatus | None = "unverified"
    lifecycle_status: LifecycleStatus = "draft"


class Goal(BaseRecord):
    record_type: RecordType = "Goal"
    direction: str = ""
    completion_criteria: list[str] = Field(default_factory=list)
    claimed_by: str | None = None
    source: str | None = None
    lifecycle_status: LifecycleStatus = "proposed"


class Constraint(BaseRecord):
    record_type: RecordType = "Constraint"
    constraint_type: str = "hard"
    description: str = ""
    lifecycle_status: LifecycleStatus = "draft"


class Experiment(BaseRecord):
    record_type: RecordType = "Experiment"
    hypothesis_refs: list[str] = Field(default_factory=list)
    discriminates_between: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    lifecycle_status: LifecycleStatus = "draft"


class DecisionRecord(BaseRecord):
    record_type: RecordType = "Decision"
    decision_type: str = "generic"
    selected_option: str | None = None
    rationale_refs: list[str] = Field(default_factory=list)
    authorized_by: list[str] = Field(default_factory=list)
    lifecycle_status: LifecycleStatus = "draft"


class ActionRecord(BaseRecord):
    record_type: RecordType = "Action"
    work_id: str = ""
    run_id: str = ""
    capability: str = ""
    provider_id: str = ""
    request_ref: str = ""
    lifecycle_status: LifecycleStatus = "recorded"


class OutcomeRecord(BaseRecord):
    record_type: RecordType = "Outcome"
    action_ref: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    lifecycle_status: LifecycleStatus = "recorded"


class RevisionRecord(BaseRecord):
    record_type: RecordType = "Revision"
    subject_ref: str = ""
    revises_ref: str | None = None
    produces_ref: str | None = None
    supersedes_ref: str | None = None
    lifecycle_status: LifecycleStatus = "proposed"


class ChangeObjectRecord(BaseRecord):
    record_type: RecordType = "ChangeObject"
    object_type: str = "generic"
    current_version_ref: str | None = None
    lifecycle_status: LifecycleStatus = "draft"


class PolicyRecord(BaseRecord):
    record_type: RecordType = "Policy"
    policy_type: str = "generic"
    rules: list[dict[str, Any]] = Field(default_factory=list)
    lifecycle_status: LifecycleStatus = "draft"


class Derivation(BaseRecord):
    """Minimal canonical inference provenance record.

    A Derivation records how a conclusion was produced; it does not own the
    conclusion's epistemic status.  That status remains on the referenced
    Assertion (or other proposition record).
    """

    record_type: RecordType = "Derivation"
    premise_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    rule_or_method_refs: list[str] = Field(default_factory=list)
    conclusion_ref: str | None = None
    provider_id: str | None = None
    domain: str | None = None
    evaluator_version: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    lifecycle_status: LifecycleStatus = "draft"


# Explicit descriptive alias used by callers that prefer the *Record suffix.
DerivationRecord = Derivation


# Convenience: KnowledgeProjection is not a record_type but a derived view (Batch5), kept here for import convenience
# but not registered as record_type.
