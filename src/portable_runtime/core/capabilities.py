from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    version: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 0
    tags: set[str] = Field(default_factory=set)
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider_id: str
    available: bool
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvocationContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    runtime_id: str
    work_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    capability: str
    work_id: str | None = None
    run_id: str | None = None
    instruction: str | None = None
    input_artifact_refs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferred_provider_ids: list[str] = Field(default_factory=list)
    excluded_provider_ids: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityResult(BaseModel):
    request_id: str
    provider_id: str
    status: Literal["succeeded", "failed", "unavailable", "needs-input", "cancelled"]
    output_artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    message: str | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
