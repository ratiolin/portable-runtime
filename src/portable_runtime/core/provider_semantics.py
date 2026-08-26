"""Explicit provider-visible operation semantics for durable invocation capture.

This module is deliberately non-executing.  A semantic contract classifies
which request/context values define reusable provider operation meaning; it
never grants qualification, authorization, retry permission, or provider
execution authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor

SemanticValueType = Literal["str", "int", "float", "bool", "json"]

# These fields may be transported to execution code but are never reusable
# operation authority.  A provider integration that really treats one of
# these values as business semantics is not compatible with this exact-replay
# substrate and must use a different, explicitly reviewed contract design.
_FORBIDDEN_REQUEST_SEMANTIC_FIELDS = frozenset(
    {
        "id",
        "work_id",
        "run_id",
        "metadata",
        "idempotency_key",
        "step_key",
        "actor_ref",
        "lease_generation",
        "lease_owner",
    }
)
_FORBIDDEN_CONTEXT_SEMANTIC_FIELDS = frozenset(
    {
        "work_id",
        "run_id",
        "metadata",
        "lease_generation",
        "idempotency_key",
    }
)

# Metadata keys that are known control-plane / qualification transport.  They
# may be present without becoming semantic identity.  Unknown metadata is not
# silently dropped: it must be declared as a typed semantic extension below.
_NON_SEMANTIC_REQUEST_METADATA = frozenset(
    {
        "authorization_refs",
        "authorization_grant_refs",
        "evidence_refs",
        "evidence_artifact_refs",
        "verification_refs",
        "verification_result_refs",
        "relation_refs",
        "record_relation_refs",
        "checkpoint_refs",
        "decision_refs",
        "obligation_refs",
        "policy_obligation_refs",
        "procedure_proof_refs",
        "qualification_refs",
        "requested_effect_class",
        "effective_impact",
        "effect_semantics",
        "procedure_profile",
        "procedure_required",
        "procedure_applicability",
        "independence_context",
        "independence_constraints",
        "actor_ref",
        "resource_ref",
        "subject_version_refs",
        "subject_refs",
        "blast_radius",
        "exposure",
        "recovery_timing",
    }
)
_NON_SEMANTIC_CONTEXT_METADATA = frozenset()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical_json(value)
    return hashlib.sha256(raw.encode()).hexdigest()


def _validate_typed_value(name: str, value: Any, declared: SemanticValueType) -> None:
    valid = {
        "str": isinstance(value, str),
        "int": isinstance(value, int) and not isinstance(value, bool),
        "float": isinstance(value, (int, float)) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "json": isinstance(value, (str, int, float, bool, list, dict)) or value is None,
    }[declared]
    if not valid:
        raise ValueError(
            f"provider semantic extension {name!r} does not satisfy declared type {declared!r}"
        )


class ProviderSemanticContract(BaseModel):
    """Versioned declaration of reusable provider operation semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    request_semantic_fields: tuple[str, ...] = (
        "capability",
        "instruction",
        "input_artifact_refs",
        "parameters",
        "constraints",
        "resource_ref",
        "subject_version_refs",
    )
    context_semantic_fields: tuple[str, ...] = ()
    request_metadata_extensions: dict[str, SemanticValueType] = Field(default_factory=dict)
    context_metadata_extensions: dict[str, SemanticValueType] = Field(default_factory=dict)
    request_extra_extensions: dict[str, SemanticValueType] = Field(default_factory=dict)
    context_extra_extensions: dict[str, SemanticValueType] = Field(default_factory=dict)
    transport_id: str = Field(default="python-provider-v1", min_length=1)

    @model_validator(mode="after")
    def _validate_contract(self) -> ProviderSemanticContract:
        request_fields = set(self.request_semantic_fields)
        context_fields = set(self.context_semantic_fields)
        unknown_request = request_fields - set(CapabilityRequest.model_fields)
        unknown_context = context_fields - set(InvocationContext.model_fields)
        if unknown_request:
            raise ValueError(f"unknown request semantic fields: {sorted(unknown_request)}")
        if unknown_context:
            raise ValueError(f"unknown context semantic fields: {sorted(unknown_context)}")
        forbidden_request = request_fields & _FORBIDDEN_REQUEST_SEMANTIC_FIELDS
        forbidden_context = context_fields & _FORBIDDEN_CONTEXT_SEMANTIC_FIELDS
        if forbidden_request:
            raise ValueError(
                f"runtime/authority request fields cannot be reusable provider semantics: {sorted(forbidden_request)}"
            )
        if forbidden_context:
            raise ValueError(
                f"runtime/authority context fields cannot be reusable provider semantics: {sorted(forbidden_context)}"
            )
        duplicate_request = set(self.request_metadata_extensions) & _NON_SEMANTIC_REQUEST_METADATA
        duplicate_context = set(self.context_metadata_extensions) & _NON_SEMANTIC_CONTEXT_METADATA
        if duplicate_request or duplicate_context:
            raise ValueError("qualification/runtime metadata cannot be reclassified as provider semantics")
        if set(self.request_extra_extensions) & set(CapabilityRequest.model_fields):
            raise ValueError("request extra semantic extension collides with a declared request field")
        if set(self.context_extra_extensions) & set(InvocationContext.model_fields):
            raise ValueError("context extra semantic extension collides with a declared context field")
        return self

    @property
    def digest(self) -> str:
        return _sha256(
            {
                "schema": "provider-semantic-contract-v1",
                **self.model_dump(mode="json"),
            }
        )


class ProviderSemanticProjection(BaseModel):
    """Canonical reusable operation meaning under one exact contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: str
    contract_digest: str
    canonical_payload: str

    def payload(self) -> dict[str, Any]:
        value = json.loads(self.canonical_payload)
        if not isinstance(value, dict):
            raise ValueError("provider semantic projection payload is malformed")
        return value


def _semantic_extensions(
    *,
    owner: str,
    metadata: dict[str, Any],
    allowed_nonsemantic: frozenset[str],
    declared: dict[str, SemanticValueType],
) -> dict[str, Any]:
    unknown = set(metadata) - allowed_nonsemantic - set(declared)
    if unknown:
        raise ValueError(
            f"unclassified provider-visible {owner} metadata: {sorted(unknown)}"
        )
    result: dict[str, Any] = {}
    for key, value_type in declared.items():
        if key not in metadata:
            continue
        value = metadata[key]
        _validate_typed_value(f"{owner}.metadata.{key}", value, value_type)
        result[key] = value
    return result


def _extra_semantics(
    *,
    owner: str,
    extras: dict[str, Any] | None,
    declared: dict[str, SemanticValueType],
) -> dict[str, Any]:
    actual = dict(extras or {})
    unknown = set(actual) - set(declared)
    if unknown:
        raise ValueError(
            f"unknown unclassified provider-visible {owner} extension fields: {sorted(unknown)}"
        )
    result: dict[str, Any] = {}
    for key, value_type in declared.items():
        if key not in actual:
            continue
        value = actual[key]
        _validate_typed_value(f"{owner}.{key}", value, value_type)
        result[key] = value
    return result


def project_provider_semantics(
    request: CapabilityRequest,
    context: InvocationContext,
    contract: ProviderSemanticContract,
) -> ProviderSemanticProjection:
    """Project only explicitly classified reusable provider operation meaning.

    Unknown request/context extension values fail closed.  Known qualification
    and runtime metadata is intentionally excluded from the canonical payload.
    """

    request_values = request.model_dump(mode="json", exclude_none=False)
    context_values = context.model_dump(mode="json", exclude_none=False)
    semantic_request = {
        field: request_values.get(field)
        for field in contract.request_semantic_fields
    }
    semantic_context = {
        field: context_values.get(field)
        for field in contract.context_semantic_fields
    }
    semantic_request_metadata = _semantic_extensions(
        owner="request",
        metadata=dict(request.metadata or {}),
        allowed_nonsemantic=_NON_SEMANTIC_REQUEST_METADATA,
        declared=contract.request_metadata_extensions,
    )
    semantic_context_metadata = _semantic_extensions(
        owner="context",
        metadata=dict(context.metadata or {}),
        allowed_nonsemantic=_NON_SEMANTIC_CONTEXT_METADATA,
        declared=contract.context_metadata_extensions,
    )
    semantic_request_extra = _extra_semantics(
        owner="request",
        extras=request.model_extra,
        declared=contract.request_extra_extensions,
    )
    semantic_context_extra = _extra_semantics(
        owner="context",
        extras=context.model_extra,
        declared=contract.context_extra_extensions,
    )
    payload = {
        "schema": "provider-semantic-projection-v1",
        "provider_id": contract.provider_id,
        "contract_digest": contract.digest,
        "transport_id": contract.transport_id,
        "request": semantic_request,
        "context": semantic_context,
        "request_metadata_extensions": semantic_request_metadata,
        "context_metadata_extensions": semantic_context_metadata,
        "request_extra_extensions": semantic_request_extra,
        "context_extra_extensions": semantic_context_extra,
    }
    canonical = _canonical_json(payload)
    return ProviderSemanticProjection(
        identity=f"provider_semantics_{_sha256(canonical)}",
        contract_digest=contract.digest,
        canonical_payload=canonical,
    )


class ProviderReplayBinding(BaseModel):
    """Stable local binding to the configured source-provider execution identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    provider_version: str
    provider_binding_id: str
    semantic_contract_digest: str
    descriptor_digest: str
    binding_digest: str


def build_provider_replay_binding(
    descriptor: ProviderDescriptor,
    contract: ProviderSemanticContract,
    *,
    provider_binding_id: str,
) -> ProviderReplayBinding:
    """Bind provenance more strongly than a provider-id string.

    ``provider_binding_id`` is an explicit configured stable identity.  It is
    intentionally not inferred from the mutable registry and may not collapse
    to the provider id itself.
    """

    stable_binding = provider_binding_id.strip()
    if not stable_binding or stable_binding == descriptor.id:
        raise ValueError("stable provider replay binding must be stronger than provider id")
    if descriptor.id != contract.provider_id:
        raise ValueError("provider semantic contract does not match provider descriptor")
    descriptor_payload = {
        "schema": "provider-replay-descriptor-v1",
        "provider_id": descriptor.id,
        "name": descriptor.name,
        "version": descriptor.version,
        "capabilities": sorted(descriptor.capabilities),
        "effect_semantics": descriptor.effect_semantics,
        "side_effect_class": descriptor.side_effect_class,
        "reversibility": descriptor.reversibility,
        "provider_family": descriptor.provider_family,
        "model_family": descriptor.model_family,
        "operator": descriptor.operator,
        "execution_domain": descriptor.execution_domain,
        "credential_domain": descriptor.credential_domain,
        "data_source_domain": descriptor.data_source_domain,
        "network_domain": descriptor.network_domain,
        "trust_boundary": descriptor.trust_boundary,
    }
    descriptor_digest = _sha256(descriptor_payload)
    binding_payload = {
        "schema": "provider-replay-binding-v1",
        "provider_id": descriptor.id,
        "provider_version": descriptor.version,
        "provider_binding_id": stable_binding,
        "semantic_contract_digest": contract.digest,
        "descriptor_digest": descriptor_digest,
    }
    return ProviderReplayBinding(
        provider_id=descriptor.id,
        provider_version=descriptor.version,
        provider_binding_id=stable_binding,
        semantic_contract_digest=contract.digest,
        descriptor_digest=descriptor_digest,
        binding_digest=_sha256(binding_payload),
    )
