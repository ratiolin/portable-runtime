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
    # V1.1 effect contract
    effect_semantics: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"] = "pure"
    side_effect_class: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"] = "pure"
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"] = "unknown"
    # V1.6 failure domains
    provider_family: str | None = None
    model_family: str | None = None
    operator: str | None = None
    execution_domain: str | None = None
    credential_domain: str | None = None
    data_source_domain: str | None = None
    evaluation_domain: str | None = None
    network_domain: str | None = None
    trust_boundary: str | None = None


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
    # V1.1 fencing
    lease_generation: int = 0
    idempotency_key: str | None = None


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
    # V1.1 idempotency
    idempotency_key: str | None = None
    step_key: str | None = None


class CapabilityResult(BaseModel):
    request_id: str
    provider_id: str
    status: Literal["succeeded", "failed", "unavailable", "needs-input", "cancelled", "unknown"] = "succeeded"
    output_artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    message: str | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # V1.1 reconcile hint
    external_operation_ref: str | None = None
    reconciled: bool = False
