"""Registry-authoritative configured-provider execution identity for dispatches.

A ProviderExecutionBinding identifies the configured provider execution identity
that the runtime ProviderRegistry selected for one reality-exit path. It is
durable provenance, not provider invocation/reconciliation/retry authority.

``authoritative_configuration_ref`` is a registry-owned registration input. The
binding does not independently verify that reference as external configuration
truth; its authority is limited to the ProviderRegistry registration domain.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.capabilities import ProviderDescriptor
from portable_runtime.core.models import Event

PROVIDER_EXECUTION_BINDING_SCHEMA = "provider-execution-binding-v1"
DISPATCH_COMMIT_EVENT = "InvocationDispatchCommitted"


def dispatch_has_provider_execution_binding_authority(event: object) -> bool:
    """Classify an input that attempts to carry B execution-binding authority.

    The classification is deliberately broader than the current valid dispatch
    serialization shape. A ref-only or embedded-binding-only dispatch still
    attempts to carry B authority and must not bypass direct-append/P5 gates.
    This predicate says nothing about graph validity or execution authority.
    """

    if not isinstance(event, Event):
        return False
    if event.type != DISPATCH_COMMIT_EVENT or not isinstance(event.payload, dict):
        return False
    return (
        "provider_execution_binding_ref" in event.payload
        or "provider_execution_binding" in event.payload
    )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: object) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode()).hexdigest()


def provider_execution_descriptor_digest(descriptor: ProviderDescriptor) -> str:
    payload = descriptor.model_dump(mode="json", exclude={"enabled"})
    return _sha256({"schema": "provider-execution-descriptor-v1", **payload})


def _binding_digest(
    *,
    provider_id: str,
    configured_execution_identity: str,
    authoritative_configuration_ref: str,
    descriptor_digest: str,
) -> str:
    return _sha256(
        {
            "schema": PROVIDER_EXECUTION_BINDING_SCHEMA,
            "provider_id": provider_id,
            "configured_execution_identity": configured_execution_identity,
            "authoritative_configuration_ref": authoritative_configuration_ref,
            "descriptor_digest": descriptor_digest,
        }
    )


class ProviderExecutionBinding(BaseModel):
    """Self-validating identity of one registry-configured execution target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    configured_execution_identity: str = Field(min_length=1)
    authoritative_configuration_ref: str = Field(min_length=1)
    descriptor_digest: str = Field(min_length=1)
    binding_digest: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_integrity(self) -> ProviderExecutionBinding:
        expected = _binding_digest(
            provider_id=self.provider_id,
            configured_execution_identity=self.configured_execution_identity,
            authoritative_configuration_ref=self.authoritative_configuration_ref,
            descriptor_digest=self.descriptor_digest,
        )
        if self.binding_digest != expected:
            raise ValueError("provider execution binding digest mismatch")
        if self.id != f"provider_execution_binding_{expected}":
            raise ValueError("provider execution binding identity mismatch")
        if self.configured_execution_identity == self.provider_id:
            raise ValueError("configured execution identity must be stronger than provider id")
        return self


def build_provider_execution_binding(
    descriptor: ProviderDescriptor,
    *,
    configured_execution_identity: str,
    authoritative_configuration_ref: str,
) -> ProviderExecutionBinding:
    """Build a binding from the ProviderRegistry registration path."""

    execution_identity = configured_execution_identity.strip()
    configuration_ref = authoritative_configuration_ref.strip()
    if not execution_identity or not configuration_ref:
        raise ValueError("provider execution binding requires configured identity and configuration ref")
    if execution_identity == descriptor.id:
        raise ValueError("configured execution identity must be stronger than provider id")
    descriptor_digest = provider_execution_descriptor_digest(descriptor)
    digest = _binding_digest(
        provider_id=descriptor.id,
        configured_execution_identity=execution_identity,
        authoritative_configuration_ref=configuration_ref,
        descriptor_digest=descriptor_digest,
    )
    return ProviderExecutionBinding(
        id=f"provider_execution_binding_{digest}",
        provider_id=descriptor.id,
        configured_execution_identity=execution_identity,
        authoritative_configuration_ref=configuration_ref,
        descriptor_digest=descriptor_digest,
        binding_digest=digest,
    )


def provider_execution_binding_from_dispatch(event: Event) -> ProviderExecutionBinding:
    """Decode an exact binding captured at dispatch authorization."""

    if event.type != DISPATCH_COMMIT_EVENT:
        raise ValueError("provider execution binding requires InvocationDispatchCommitted")
    payload = event.payload if isinstance(event.payload, dict) else {}
    raw = payload.get("provider_execution_binding")
    binding_ref = payload.get("provider_execution_binding_ref")
    if not isinstance(raw, dict) or not isinstance(binding_ref, str) or not binding_ref:
        raise ValueError("legacy dispatch has no original provider execution binding; backfill unsupported")
    binding = ProviderExecutionBinding.model_validate(raw)
    if binding.id != binding_ref:
        raise ValueError("dispatch provider execution binding ref mismatch")
    if binding.provider_id != payload.get("provider_id"):
        raise ValueError("dispatch provider execution binding provider mismatch")
    return binding


def reject_historical_execution_binding_backfill(*_args: object, **_kwargs: object) -> None:
    raise ValueError("historical provider execution binding backfill from current state is unsupported")


@dataclass(frozen=True)
class HistoricalTargetResolution:
    status: str
    allowed: bool
    retargeted: bool = False
    reason: str = ""


def resolve_historical_reconciliation_target(
    historical: ProviderExecutionBinding,
    current: ProviderExecutionBinding | None,
) -> HistoricalTargetResolution:
    """Compare historical identity to a separately resolved registry binding."""

    if current is None:
        return HistoricalTargetResolution(
            status="unavailable",
            allowed=False,
            reason="exact historical configured provider is unavailable",
        )
    if current != historical:
        return HistoricalTargetResolution(
            status="mismatch",
            allowed=False,
            reason="current configured provider does not match historical execution binding",
        )
    return HistoricalTargetResolution(status="resolved", allowed=True)


@dataclass(frozen=True)
class HistoricalTargetCaptureState:
    target_status: str
    automated_reconciliation_allowed: bool


def classify_historical_target_capture(
    *,
    reality_exit_may_have_occurred: bool,
    durable_execution_binding_ref: str | None,
) -> HistoricalTargetCaptureState:
    if reality_exit_may_have_occurred and not durable_execution_binding_ref:
        return HistoricalTargetCaptureState("unknowable", False)
    return HistoricalTargetCaptureState(
        "known" if durable_execution_binding_ref else "not-yet-exited",
        bool(durable_execution_binding_ref),
    )
