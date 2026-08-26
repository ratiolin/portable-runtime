"""B4 configured-provider reconciliation target audit.

Audit only. This file authorizes no provider-target production/schema, dispatch
change, registry authority, provider call, repeatability production,
application-binding production, Runtime consumption, retry, DIS-015, PVP-007,
historical backfill, or P5 import authority.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import ProviderDescriptor
from portable_runtime.core.provider_semantics import ProviderReplayBinding
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance import dispatch as dispatch_module
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.workflows.invocation_specification import InvocationSpecificationCommitRequest


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


class _ReplacementProvider:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.descriptor = ProviderDescriptor(
            id="provider:target-audit",
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
        return None

    async def reconcile(self, request_id: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def test_pt_audit_dispatch_payload_has_provider_id_but_no_execution_binding() -> None:
    source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert '"provider_id": permit.provider_id' in source
    assert "provider_execution_binding" not in source
    assert "configured_provider" not in source


def test_pt_audit_dispatch_identity_has_no_execution_binding() -> None:
    source = inspect.getsource(dispatch_module._dispatch_commit_ref)
    assert '"provider_id": permit.provider_id' in source
    assert "provider_execution_binding" not in source
    assert "configured_provider" not in source


def test_pt_audit_registry_get_is_current_live_object_resolution() -> None:
    registry = ProviderRegistry()
    first = _ReplacementProvider("v1")
    registry.register(first)  # type: ignore[arg-type]
    assert registry.get(first.descriptor.id) is first


def test_pt_audit_registry_allows_same_id_replacement_after_unregister() -> None:
    registry = ProviderRegistry()
    first = _ReplacementProvider("v1")
    second = _ReplacementProvider("v2")
    registry.register(first)  # type: ignore[arg-type]
    registry.unregister(first.descriptor.id)
    registry.register(second)  # type: ignore[arg-type]
    assert registry.get(second.descriptor.id) is second
    assert first is not second


def test_pt_audit_reality_boundary_reconcile_resolves_current_provider_id() -> None:
    source = inspect.getsource(RealityBoundary.reconcile)
    assert "registry.get(provider_id)" in source
    assert "provider_execution_binding" not in source
    assert "configured_provider" not in source


def test_pt_audit_local_provider_replay_binding_disclaims_registry_authority() -> None:
    doc = inspect.getdoc(ProviderReplayBinding) or ""
    assert "not proof" in doc.lower()
    assert "authoritative configured provider instance" in doc.lower()


def test_pt_audit_invocation_spec_binding_id_is_capture_caller_input() -> None:
    fields = set(InvocationSpecificationCommitRequest.model_fields)
    assert "provider_binding_id" in fields
    assert "provider_execution_binding_ref" not in fields


def test_pt_audit_provider_descriptor_has_no_execution_binding_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "provider_execution_binding" not in fields
    assert "configured_execution_identity" not in fields
    assert "execution_binding_digest" not in fields


def test_pt_audit_no_provider_execution_binding_production_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.governance.provider_execution_binding") is None


@_xfail("B4 PT-001: provider_id is not historical configured-provider execution identity")
def test_pt_001_provider_id_is_not_historical_execution_identity() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="provider.*id|execution.*identity|binding"):
        module.ProviderExecutionBinding.from_provider_id("provider:a")


@_xfail("B4 PT-002: current registry object is not historical target authority")
def test_pt_002_current_registry_object_is_not_historical_authority() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    registry = ProviderRegistry()
    current = _ReplacementProvider("current")
    registry.register(current)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="historical|authority|binding"):
        module.binding_from_current_registry(registry, current.descriptor.id)


@_xfail("B4 PT-003: same-id provider replacement cannot satisfy historical binding")
def test_pt_003_same_id_replacement_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    source = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:source",
    )
    replacement = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:replacement",
    )
    with pytest.raises(ValueError, match="mismatch|binding|identity|replacement"):
        module.assert_same_historical_target(source, replacement)


@_xfail("B4 PT-004: descriptor equality alone is not configured execution identity")
def test_pt_004_descriptor_equality_is_not_execution_identity() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    descriptor = ProviderDescriptor(
        id="provider:a",
        name="same",
        version="1",
        capabilities=["deploy.apply"],
    )
    with pytest.raises(ValueError, match="configured|execution|authority|binding"):
        module.ProviderExecutionBinding.from_descriptor(descriptor)


@_xfail("B4 PT-005: local ProviderReplayBinding representation is not execution authority")
def test_pt_005_provider_replay_binding_cannot_be_promoted_to_execution_authority() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="replay|execution|authority"):
        module.promote_provider_replay_binding("provider_replay_binding:declared")


@_xfail("B4 PT-006: caller cannot manufacture configured-provider execution binding")
def test_pt_006_caller_cannot_supply_execution_binding_string() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    fields = set(module.ProviderExecutionBindingCommitRequest.model_fields)
    assert "configured_execution_identity" not in fields
    assert "binding_digest" not in fields


@_xfail("B4 PT-007: binding must originate from authoritative configured-provider path")
def test_pt_007_binding_origin_is_authoritative_configuration_path() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    fixture = module.ProviderExecutionBindingAuditFixture.example()
    binding = fixture.capture_from_authoritative_selection()
    assert binding.authoritative_configuration_ref == fixture.configuration_ref
    assert binding.provider_id == fixture.provider_id


@_xfail("B4 PT-008: historical binding cannot be backfilled from current registry/configuration")
def test_pt_008_historical_backfill_from_current_registry_is_closed() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="historical|backfill|current|authority"):
        module.backfill_historical_execution_binding(
            dispatch_ref="dispatch:legacy",
            provider_id="provider:a",
            current_configuration_ref="provider-config:current",
        )


@_xfail("B4 PT-009: configured execution binding drift under same provider_id is detectable")
def test_pt_009_same_provider_id_binding_drift_is_detected() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    source = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:source",
    )
    current = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:changed",
    )
    eligibility = module.resolve_historical_reconciliation_target(source, current)
    assert eligibility.allowed is False
    assert "mismatch" in eligibility.reason.lower() or "drift" in eligibility.reason.lower()


@_xfail("B4 PT-010: exact historical binding with no current resolver is unavailable, not retargeted")
def test_pt_010_missing_current_target_is_unavailable() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    source = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:source",
    )
    result = module.resolve_historical_reconciliation_target(source, current_binding=None)
    assert result.allowed is False
    assert result.status == "unavailable"
    assert result.retargeted is False


@_xfail("B4 PT-011: same-id but mismatched current provider fails closed")
def test_pt_011_mismatched_current_provider_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    source = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:source",
    )
    current = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:other",
    )
    with pytest.raises(ValueError, match="target|mismatch|identity|binding"):
        module.require_exact_historical_target(source, current)


@_xfail("B4 PT-012: execution binding identity alone does not authorize provider.reconcile")
def test_pt_012_execution_binding_does_not_authorize_reconcile() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    binding = module.ProviderExecutionBinding.example()
    assert not hasattr(binding, "reconcile")
    assert not hasattr(binding, "consume_recovery_application")


@_xfail("B4 PT-013: execution binding does not authorize provider.invoke or business retry")
def test_pt_013_execution_binding_does_not_authorize_invoke_or_retry() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    binding = module.ProviderExecutionBinding.example()
    assert not hasattr(binding, "invoke")
    assert not hasattr(binding, "retry")
    assert not hasattr(binding, "materialize_capability_request")


@_xfail("B4 PT-014: execution binding does not imply reconciliation repeatability")
def test_pt_014_execution_binding_does_not_imply_repeatability() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    binding = module.ProviderExecutionBinding.example()
    assert not hasattr(binding, "repeat_safe")
    assert not hasattr(binding, "reconciliation_repeatability_contract")


@_xfail("B4 PT-015: legacy dispatch without original binding remains non-upgradable")
def test_pt_015_legacy_dispatch_remains_non_upgradable() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="legacy|historical|binding|unsupported"):
        module.execution_binding_from_dispatch(
            dispatch_ref="dispatch:legacy-provider-id-only",
            allow_backfill=False,
        )


@_xfail("B4 PT-016: serialized/import provider execution-binding authority remains P5-closed")
def test_pt_016_serialized_binding_import_is_closed() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="import|serialized|P5|unsupported"):
        module.import_provider_execution_binding_authority(
            {"provider_id": "provider:a", "configured_execution_identity": "configured:a"}
        )


@_xfail("B4 PT-017: reality exit without durable exact binding makes historical target unknowable")
def test_pt_017_reality_exit_without_durable_binding_blocks_automated_reconciliation() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    state = module.classify_historical_target_capture(
        reality_exit_may_have_occurred=True,
        durable_execution_binding_ref=None,
    )
    assert state.target_status == "unknowable"
    assert state.automated_reconciliation_allowed is False
