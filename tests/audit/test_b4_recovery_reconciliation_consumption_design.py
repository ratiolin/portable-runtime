"""B4 reconciliation-consumption design audit graduation.

The original audit froze RC-001..016 before production authority existed.
Production now lives in ``workflows.reconciliation_consumer`` and the original
hypothetical ``workflows.recovery_reconciliation`` module remains absent.
These tests preserve the historical distinctions while asserting the current
closed V1 authority topology.
"""

from __future__ import annotations

import importlib.util
import inspect

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import ProviderDescriptor
from portable_runtime.core.reconciliation_boundary import (
    RecoveryReconciliationRealityBoundary,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.workflows.reconciliation_consumer import (
    RecoveryReconciliationConsumer,
    RecoveryReconciliationRequest,
)
from portable_runtime.workflows.recovery_application import RecoveryApplication
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservation,
    RecoveryObservationCommitRequest,
)


class _ReplacementProvider:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.descriptor = ProviderDescriptor(
            id="provider:reconcile-audit",
            name=f"provider-{marker}",
            version=marker,
            capabilities=["deploy.apply"],
            effect_semantics="reconcilable",
            side_effect_class="reconcilable",
        )

    async def health(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def invoke(self, request, context):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str):  # type: ignore[no-untyped-def]
        del request_id
        raise AssertionError("audit helper does not cross reality boundary")


def test_rc_audit_runtime_reconcile_remains_step_id_compatibility_surface() -> None:
    signature = inspect.signature(Runtime.reconcile)
    assert list(signature.parameters) == ["self", "step_id"]
    source = inspect.getsource(Runtime.reconcile)
    assert "list_attempts(step_id)" in source
    assert "self.capabilities.reconcile" not in source
    assert "commit_recovery_observation" not in source
    assert "compatibility-only" in source


def test_rc_audit_legacy_reality_boundary_still_relooks_up_provider_id() -> None:
    signature = inspect.signature(RealityBoundary.reconcile)
    assert {"request_id", "provider_id"} <= set(signature.parameters)
    source = inspect.getsource(RealityBoundary.reconcile)
    assert "registry.get(provider_id)" in source
    assert "reconcile(request_id)" in source


def test_rc_audit_authoritative_consumer_never_uses_legacy_boundary_reconcile() -> None:
    source = inspect.getsource(RecoveryReconciliationConsumer.consume)
    assert "reconcile_exact_target" in source
    assert "self.reality_boundary.reconcile(" not in source


def test_rc_audit_exact_target_boundary_has_no_provider_id_lookup() -> None:
    source = inspect.getsource(
        RecoveryReconciliationRealityBoundary.reconcile_exact_target
    )
    assert "registry.get" not in source
    assert "self.registry" not in source
    assert "await reconcile(request_id)" in source


def test_rc_audit_consumer_request_surface_is_exact_application_ref_only() -> None:
    assert set(RecoveryReconciliationRequest.__dataclass_fields__) == {
        "recovery_application_ref"
    }


def test_rc_audit_provider_protocol_still_has_no_repeatability_bool_authority() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconcile_repeat_safe" not in fields
    assert "reconciliation_idempotent" not in fields


def test_rc_audit_registry_same_id_replacement_is_not_identity_equality() -> None:
    registry = ProviderRegistry()
    first = _ReplacementProvider("v1")
    second = _ReplacementProvider("v2")
    registry.register(first)  # type: ignore[arg-type]
    assert registry.get(first.descriptor.id) is first
    registry.unregister(first.descriptor.id)
    registry.register(second)  # type: ignore[arg-type]
    assert registry.get(second.descriptor.id) is second
    assert first is not second


def test_rc_audit_application_carries_source_provider_id_not_caller_binding() -> None:
    fields = set(RecoveryApplication.__dataclass_fields__)
    assert {
        "application_kind",
        "source_dispatch_ref",
        "source_attempt_ref",
        "source_action_ref",
        "source_request_ref",
        "source_provider_id",
    } <= fields
    assert "source_provider_binding" not in fields
    assert "source_provider_binding_digest" not in fields
    assert "configured_provider_ref" not in fields


def test_rc_audit_generic_observation_request_cannot_manufacture_a_binding() -> None:
    request_fields = set(RecoveryObservationCommitRequest.__dataclass_fields__)
    observation_fields = set(RecoveryObservation.__dataclass_fields__)
    assert "recovery_application_ref" not in request_fields
    assert "recovery_application_ref" in observation_fields
    assert "provenance_refs" in request_fields


def test_rc_audit_runtime_no_longer_creates_generic_reconcile_observation_instances() -> None:
    source = inspect.getsource(Runtime.reconcile)
    assert "recovery_observation_instance" not in source
    assert "commit_recovery_observation" not in source


def test_rc_audit_local_invocation_specification_is_not_consumer_authority() -> None:
    runtime_source = inspect.getsource(Runtime.reconcile)
    boundary_source = inspect.getsource(RealityBoundary.reconcile)
    consumer_source = inspect.getsource(RecoveryReconciliationConsumer.consume)
    assert "invocation_spec" not in runtime_source
    assert "invocation_spec" not in boundary_source
    assert "invocation_spec" not in consumer_source


def test_rc_audit_original_hypothetical_module_name_remains_absent() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation") is None


def test_rc_audit_production_consumer_module_is_present() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.reconciliation_consumer") is not None


def test_rc_audit_consumer_creates_no_attempt_or_consumed_fact_types() -> None:
    source = inspect.getsource(RecoveryReconciliationConsumer)
    assert "RecoveryReconciliationAttemptRecorded" not in source
    assert "RecoveryApplicationConsumed" not in source
    assert "GovernanceDispatchCommitter" not in source
    assert ".invoke(" not in source
