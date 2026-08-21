"""Reopen — R1.5 implementation milestone."""

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


class ReopenAssemblyError(ValueError):
    """Authoritative semantic graph required to assemble a reopen package."""


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


class ReopenAssembler:
    """Resolve reopen responsibility from the authoritative semantic graph.

    Work metadata is intentionally not consulted.  It may remain useful to a
    UI as a cache/display hint, but it cannot become a canonical handoff fact.
    """

    def __init__(self, store: Any | None) -> None:
        self.store = store

    def _records_and_relations(self, assessment: ReopenAssessment, original_work: Work) -> tuple[dict[str, Any], list[Any]]:
        if self.store is None:
            return {}, []
        records: dict[str, Any] = {}
        relations = list(self.store.list_relations()) if hasattr(self.store, "list_relations") else []
        queue = [original_work.id, assessment.record_ref or original_work.id]
        seen = set(queue)
        while queue:
            current = queue.pop(0)
            for rel in relations:
                if rel.subject_ref != current and rel.object_ref != current:
                    continue
                other = rel.object_ref if rel.subject_ref == current else rel.subject_ref
                if other in seen:
                    continue
                candidate = self.store.get_record(other) if hasattr(self.store, "get_record") else None
                if candidate is None and hasattr(self.store, "get_authorization"):
                    candidate = self.store.get_authorization(other)
                if candidate is None:
                    continue
                seen.add(other)
                queue.append(other)
                records[other] = candidate
        target = self.store.get_record(assessment.record_ref) if hasattr(self.store, "get_record") else None
        if target is not None:
            records[assessment.record_ref] = target
        return records, relations

    @staticmethod
    def _record_type(value: Any) -> str:
        return str(getattr(value, "record_type", "") or value.__class__.__name__)

    def assemble(
        self,
        assessment: ReopenAssessment,
        original_work: Work,
        *,
        handoff: HandoffEnvelope | None = None,
    ) -> ReopenPackage:
        records, relations = self._records_and_relations(assessment, original_work)
        if self.store is None and handoff is None and assessment.handoff is None:
            raise ReopenAssemblyError(
                "authoritative store or explicit handoff envelope is required for reopen assembly"
            )

        evidence_refs: list[str] = []
        observation_refs: list[str] = []
        assertion_refs: list[str] = []
        goal_refs: list[str] = []
        constraint_refs: list[str] = []
        authorization_refs: list[str] = []
        candidate_refs: list[str] = []
        rejected_refs: list[str] = []
        counterevidence_refs: list[str] = []
        assumptions: list[str] = []
        unknown_scopes: list[str] = []
        reopen_condition_refs: list[str] = []
        invalidation_refs: list[str] = []
        closure_refs: list[str] = []
        environment_versions: dict[str, str] = {}
        scope: dict[str, Any] = {}
        dispositions: dict[str, HandoffDisposition] = {}

        for ref, record in records.items():
            record_type = self._record_type(record)
            lifecycle = str(getattr(record, "lifecycle_status", "") or "")
            if record_type == "EvidenceArtifact":
                evidence_refs.append(ref)
            elif record_type == "Observation":
                observation_refs.append(ref)
            elif record_type == "Assertion":
                assertion_refs.append(ref)
            elif record_type == "Goal":
                goal_refs.append(ref)
            elif record_type == "Constraint":
                constraint_refs.append(ref)
            elif record_type == "AuthorizationGrant":
                authorization_refs.append(ref)
            if lifecycle == "candidate":
                candidate_refs.append(ref)
            if lifecycle in {"rejected", "deprecated", "archived"}:
                rejected_refs.append(ref)
            if lifecycle in {"verified", "accepted", "confirmed", "official"}:
                closure_refs.append(ref)
            assumptions.extend(str(item) for item in (getattr(record, "assumptions", None) or []) if str(item).strip())
            unknown_scopes.extend(str(item) for item in (getattr(record, "unknown_scopes", None) or []) if str(item).strip())
            reopen_condition_refs.extend(str(item) for item in (getattr(record, "invalidation_conditions", None) or []) if str(item).strip())
            environment_versions.update(dict(getattr(record, "environment_versions", None) or {}))
            if not scope and isinstance(getattr(record, "scope", None), dict):
                scope = dict(record.scope)
            dispositions[ref] = "invalidated" if lifecycle in {"rejected", "deprecated", "archived", "superseded"} else "carry-forward"

        for rel in relations:
            if rel.subject_ref not in records and rel.object_ref not in records:
                continue
            if rel.relation_type == "authorizes":
                authorization_refs.extend([ref for ref in (rel.subject_ref, rel.object_ref) if ref in records])
            elif rel.relation_type == "contradicts":
                counterevidence_refs.extend([ref for ref in (rel.subject_ref, rel.object_ref) if ref in records])
                for ref in (rel.subject_ref, rel.object_ref):
                    if ref in records:
                        dispositions[ref] = "invalidated"
            elif rel.relation_type == "requires-revalidation":
                invalidation_refs.append(rel.id)
                if rel.subject_ref in records:
                    dispositions[rel.subject_ref] = "reconsider"
            elif rel.relation_type == "supports":
                for ref in (rel.subject_ref, rel.object_ref):
                    if ref in records and self._record_type(records[ref]) == "Assertion":
                        assertion_refs.append(ref)

        def unique(values: list[str]) -> list[str]:
            return list(dict.fromkeys(values))
        handoff_envelope = handoff or assessment.handoff or HandoffEnvelope(
            subject_refs=unique([original_work.id, assessment.record_ref or original_work.id]),
            goal_refs=unique(goal_refs),
            constraint_refs=unique(constraint_refs),
            assumption_refs=unique(assumptions),
            evidence_refs=unique(evidence_refs),
            observation_refs=unique(observation_refs),
            current_assertion_refs=unique(assertion_refs),
            unknown_refs=unique(unknown_scopes),
            counterevidence_refs=unique(counterevidence_refs),
            still_qualified_candidate_refs=unique(candidate_refs),
            authorization_refs=unique(authorization_refs),
            closure_refs=unique(closure_refs),
            invalidation_refs=unique(invalidation_refs),
            reopen_condition_refs=unique(reopen_condition_refs),
            dispositions=dispositions,
        )
        return ReopenPackage(
            original_work_ref=original_work.id,
            target_record_ref=assessment.record_ref or original_work.id,
            current_conclusion_refs=unique(assertion_refs),
            scope=scope,
            assumptions=unique(assumptions),
            evidence_refs=unique(evidence_refs),
            counterevidence_refs=unique(counterevidence_refs),
            unknown_scopes=unique(unknown_scopes),
            still_qualified_candidate_refs=unique(candidate_refs),
            rejected_candidate_refs=unique(rejected_refs),
            acceptance_criteria=list(original_work.acceptance_criteria),
            constraints=dict(original_work.constraints),
            inputs=list(original_work.inputs),
            artifact_refs=list(original_work.artifact_refs),
            reopen_reason=assessment.reason,
            revision_scope=assessment.revision_scope,
            environment_versions=environment_versions,
            authorization_context={"authorization_refs": unique(authorization_refs)},
            failure_history_refs=unique(invalidation_refs),
            handoff=handoff_envelope,
        )


def build_reopen_package(
    assessment: ReopenAssessment,
    original_work: Work,
    *,
    handoff: HandoffEnvelope | None = None,
    store: Any | None = None,
) -> ReopenPackage:
    """Build an explicit handoff package from the authoritative graph."""
    return ReopenAssembler(store).assemble(assessment, original_work, handoff=handoff)

def create_reopen_work(assessment: ReopenAssessment, original_work: Work, *, store: Any | None = None) -> Work:
    """Create superseding Work for reopen; preserves old history via supersedes relation."""
    package = assessment.package or build_reopen_package(assessment, original_work, store=store)
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
