from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("obj"))
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Work(RuntimeModel):
    """Canonical unit of work; it never contains a provider prompt."""

    kind: str = "generic-task"
    title: str
    description: str = ""
    status: Literal[
        "open",
        "ready",
        "running",
        "blocked",
        "waiting",
        "completed",
        "failed",
        "cancelled",
        "archived",
    ] = "open"
    priority: int = 0
    inputs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)
    parent_work_id: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class Run(RuntimeModel):
    work_id: str
    status: Literal[
        "queued",
        "running",
        "waiting",
        "blocked",
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
    ] = "queued"
    workflow_id: str = "generic-task"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    current_step: str | None = None
    provider_invocation_refs: list[str] = Field(default_factory=list)
    # V1.1 lease/fencing for recovery
    lease_owner: str | None = None
    lease_generation: int = 0
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None


class Artifact(RuntimeModel):
    kind: str
    media_type: str | None = None
    uri: str | None = None
    inline_data: Any | None = None
    created_by_run_id: str | None = None
    created_by_provider_id: str | None = None
    checksum: str | None = None


class Evidence(RuntimeModel):
    kind: str
    subject_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    source: str
    observed_at: datetime = Field(default_factory=utcnow)
    status: Literal[
        "unverified",
        "supported",
        "contested",
        "refuted",
        "unknown",
        "revalidation-required",
    ] = "unverified"


class Decision(RuntimeModel):
    work_id: str
    decision_type: str
    selected_option: str | None = None
    rationale_artifact_refs: list[str] = Field(default_factory=list)
    authorized_by: list[str] = Field(default_factory=list)


class Action(RuntimeModel):
    work_id: str
    run_id: str
    capability: str
    provider_id: str
    request_ref: str
    status: str = "queued"


class Outcome(RuntimeModel):
    action_id: str
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    status: str


class KnowledgeItem(RuntimeModel):
    kind: str
    title: str
    content_ref: str
    status: Literal["candidate", "official", "deprecated", "archived"] = "candidate"
    source_work_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    valid_scope: dict[str, Any] = Field(default_factory=dict)
    reopen_conditions: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)


class Event(RuntimeModel):
    type: str
    subject_ref: str
    payload: dict[str, Any] = Field(default_factory=dict)


# V1.1 Execution Integrity models

class Step(RuntimeModel):
    """Durable step within a Run; crash-recoverable."""

    run_id: str
    step_key: str
    kind: str = "generic"
    status: Literal[
        "pending",
        "ready",
        "running",
        "waiting",
        "succeeded",
        "failed",
        "cancelled",
        "compensating",
        "compensated",
        "unknown",
    ] = "pending"
    input_digest: str | None = None
    side_effect_class: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"] = "pure"
    effect_semantics: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"] = "pure"
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"] = "unknown"
    current_attempt: int = 0
    version: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
    lease_owner: str | None = None
    lease_generation: int = 0
    lease_expires_at: datetime | None = None


class StepAttempt(RuntimeModel):
    step_id: str
    attempt_no: int = 1
    provider_id: str | None = None
    request_ref: str | None = None
    idempotency_key: str | None = None
    external_operation_ref: str | None = None
    started_at: datetime | None = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    status: Literal["running", "succeeded", "failed", "cancelled", "unknown"] = "running"
    result_ref: str | None = None
    error: dict[str, Any] | None = None
    lease_generation: int = 0


class Checkpoint(RuntimeModel):
    run_id: str
    step_id: str | None = None
    state_digest: str | None = None
    payload_ref: str | None = None
    payload: dict[str, Any] | None = None


class Compensation(RuntimeModel):
    action_ref: str
    compensation_capability: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"] = "pending"
    started_at: datetime | None = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    result_ref: str | None = None

