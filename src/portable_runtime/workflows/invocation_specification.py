"""Local durable, non-executing invocation specification authority.

A DurableInvocationSpecification preserves reusable provider operation meaning,
source provenance and replay identity. It deliberately does not materialize a
fresh request, issue a permit, create an Attempt/dispatch, or invoke a provider.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor
from portable_runtime.core.models import Event
from portable_runtime.core.provider_semantics import (
    ProviderReplayBinding,
    ProviderSemanticContract,
    ProviderSemanticProjection,
    build_provider_replay_binding,
    project_provider_semantics,
)

INVOCATION_SPECIFICATION_EVENT = "InvocationSpecificationRecorded"
INVOCATION_SPECIFICATION_SCHEMA = "durable-invocation-specification-v1"
_RETRY_IDEMPOTENT_SEMANTICS = frozenset({"idempotent", "deduplicatable"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical_json(value)
    return hashlib.sha256(raw.encode()).hexdigest()


class InvocationSpecificationCommitRequest(BaseModel):
    """Request initial authoritative capture of one exact invocation meaning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: CapabilityRequest
    context: InvocationContext
    provider_descriptor: ProviderDescriptor
    semantic_contract: ProviderSemanticContract
    provider_binding_id: str


class DurableInvocationSpecification(BaseModel):
    """Immutable local specification/provenance authority, not execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    semantic_identity: str
    canonical_semantic_payload: str
    semantic_contract_digest: str
    provider_binding: ProviderReplayBinding
    source_request_ref: str
    source_work_ref: str | None = None
    source_run_ref: str | None = None
    idempotency_key: str | None = None
    effect_semantics: str

    @model_validator(mode="after")
    def _validate_internal_integrity(self) -> DurableInvocationSpecification:
        """Close semantic payload/contract/provider binding into one graph.

        ProviderSemanticProjection owns the canonical-payload -> identity and
        payload -> contract-digest rules. Reusing that validator here avoids a
        second hash implementation at the durable specification boundary.
        """

        projection = ProviderSemanticProjection(
            identity=self.semantic_identity,
            contract_digest=self.semantic_contract_digest,
            canonical_payload=self.canonical_semantic_payload,
        )
        if self.provider_binding.semantic_contract_digest != self.semantic_contract_digest:
            raise ValueError(
                "InvocationSpecification semantic contract does not match provider replay binding"
            )
        projection_provider = projection.payload().get("provider_id")
        if projection_provider != self.provider_binding.provider_id:
            raise ValueError(
                "InvocationSpecification semantic provider does not match provider replay binding"
            )
        return self


@dataclass(frozen=True)
class InvocationSpecificationCommitPlan:
    specification: DurableInvocationSpecification
    event: Event | None
    replayed: bool


def _specification_identity_payload(
    *,
    semantic_identity: str,
    semantic_contract_digest: str,
    provider_binding: ProviderReplayBinding,
    source_request_ref: str,
    source_work_ref: str | None,
    source_run_ref: str | None,
    idempotency_key: str | None,
    effect_semantics: str,
) -> dict[str, Any]:
    # The semantic identity is content-addressed independently. The durable
    # authority instance additionally binds exact source/replay provenance so
    # a different historical request cannot silently become the same fact.
    return {
        "schema": INVOCATION_SPECIFICATION_SCHEMA,
        "semantic_identity": semantic_identity,
        "semantic_contract_digest": semantic_contract_digest,
        "provider_binding_digest": provider_binding.binding_digest,
        "source_request_ref": source_request_ref,
        "source_work_ref": source_work_ref,
        "source_run_ref": source_run_ref,
        "idempotency_key": idempotency_key,
        "effect_semantics": effect_semantics,
    }


def build_invocation_specification(
    request: CapabilityRequest,
    context: InvocationContext,
    provider_descriptor: ProviderDescriptor,
    semantic_contract: ProviderSemanticContract,
    *,
    provider_binding_id: str,
) -> DurableInvocationSpecification:
    """Build one deterministic non-executing specification candidate."""

    if provider_descriptor.id != semantic_contract.provider_id:
        raise ValueError("provider semantic contract does not match selected provider")
    if request.capability not in provider_descriptor.capabilities:
        raise ValueError("provider descriptor does not advertise the request capability")
    projection = project_provider_semantics(request, context, semantic_contract)
    provider_binding = build_provider_replay_binding(
        provider_descriptor,
        semantic_contract,
        provider_binding_id=provider_binding_id,
    )
    effect_semantics = provider_descriptor.effect_semantics
    idempotency_key = request.idempotency_key
    if effect_semantics in _RETRY_IDEMPOTENT_SEMANTICS and not idempotency_key:
        raise ValueError(
            "retry-eligible side-effect invocation specification requires exact idempotency identity"
        )
    identity_payload = _specification_identity_payload(
        semantic_identity=projection.identity,
        semantic_contract_digest=projection.contract_digest,
        provider_binding=provider_binding,
        source_request_ref=request.id,
        source_work_ref=request.work_id,
        source_run_ref=request.run_id,
        idempotency_key=idempotency_key,
        effect_semantics=effect_semantics,
    )
    specification_id = f"invocation_spec_{_digest(identity_payload)}"
    return DurableInvocationSpecification(
        id=specification_id,
        semantic_identity=projection.identity,
        canonical_semantic_payload=projection.canonical_payload,
        semantic_contract_digest=projection.contract_digest,
        provider_binding=provider_binding,
        source_request_ref=request.id,
        source_work_ref=request.work_id,
        source_run_ref=request.run_id,
        idempotency_key=idempotency_key,
        effect_semantics=effect_semantics,
    )


def invocation_specification_event(specification: DurableInvocationSpecification) -> Event:
    return Event(
        id=specification.id,
        type=INVOCATION_SPECIFICATION_EVENT,
        subject_ref=specification.source_request_ref,
        payload={
            "schema": INVOCATION_SPECIFICATION_SCHEMA,
            "specification": specification.model_dump(mode="json"),
        },
    )


def invocation_specification_from_event(event: Event) -> DurableInvocationSpecification:
    if event.type != INVOCATION_SPECIFICATION_EVENT:
        raise ValueError("event is not an InvocationSpecification authority fact")
    if event.payload.get("schema") != INVOCATION_SPECIFICATION_SCHEMA:
        raise ValueError("unsupported InvocationSpecification schema")
    raw = event.payload.get("specification")
    if not isinstance(raw, dict):
        raise ValueError("InvocationSpecification event is missing specification payload")
    # DurableInvocationSpecification validation reuses ProviderSemanticProjection
    # validation, so decode cannot accept a payload/identity/contract/provider
    # combination whose individual hashes are valid but whose graph is not.
    specification = DurableInvocationSpecification.model_validate(raw)
    if specification.id != event.id:
        raise ValueError("InvocationSpecification event/specification identity mismatch")
    if specification.source_request_ref != event.subject_ref:
        raise ValueError("InvocationSpecification event/source request binding mismatch")
    identity_payload = _specification_identity_payload(
        semantic_identity=specification.semantic_identity,
        semantic_contract_digest=specification.semantic_contract_digest,
        provider_binding=specification.provider_binding,
        source_request_ref=specification.source_request_ref,
        source_work_ref=specification.source_work_ref,
        source_run_ref=specification.source_run_ref,
        idempotency_key=specification.idempotency_key,
        effect_semantics=specification.effect_semantics,
    )
    expected = f"invocation_spec_{_digest(identity_payload)}"
    if specification.id != expected:
        raise ValueError("InvocationSpecification deterministic identity rebound")
    return specification


def same_invocation_specification_semantics(
    left: DurableInvocationSpecification,
    right: DurableInvocationSpecification,
) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")


def prepare_invocation_specification_commit(
    store: Any,
    request: InvocationSpecificationCommitRequest,
) -> InvocationSpecificationCommitPlan:
    """Prepare store-owned commit/replay without creating execution authority."""

    specification = build_invocation_specification(
        request.request,
        request.context,
        request.provider_descriptor,
        request.semantic_contract,
        provider_binding_id=request.provider_binding_id,
    )
    event = invocation_specification_event(specification)
    existing = store.get_event(event.id) if hasattr(store, "get_event") else None
    if existing is None:
        return InvocationSpecificationCommitPlan(specification, event, False)
    persisted = invocation_specification_from_event(existing)
    if not same_invocation_specification_semantics(persisted, specification):
        raise ValueError("InvocationSpecification deterministic identity rebound")
    return InvocationSpecificationCommitPlan(persisted, None, True)


def reject_historical_specification_backfill(*, request_ref: str, dispatch_ref: str) -> None:
    """Permanent fail-closed boundary for history lacking original spec binding."""

    raise ValueError(
        f"historical InvocationSpecification backfill is unsupported for {request_ref!r}/{dispatch_ref!r}"
    )
