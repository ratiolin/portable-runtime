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
