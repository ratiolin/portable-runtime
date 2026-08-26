"""B4 reconciliation-only RecoveryApplication consumption audit.

Audit only. This file authorizes no reconciliation consumption production,
provider-binding production, repeatability protocol, RecoveryObservation schema
change, Runtime integration, retry, fresh invocation authority, or P5 import.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import CapabilityResult, ProviderDescriptor
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.workflows.recovery_application import RecoveryApplication
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservation,
    RecoveryObservationCommitRequest,
)


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


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
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult:
        return CapabilityResult(
            request_id=request_id,
            provider_id=self.descriptor.id,
            status="unknown",
            metadata={"provider_marker": self.marker},
        )


def test_rc_audit_runtime_reconcile_is_still_step_id_utility_surface() -> None:
    signature = inspect.signature(Runtime.reconcile)
    assert list(signature.parameters) == ["self", "step_id"]
    source = inspect.getsource(Runtime.reconcile)
    assert "list_attempts(step_id)" in source
    assert "self.capabilities.reconcile(last.request_ref, last.provider_id)" in source
    assert "RecoveryApplication" not in source


def test_rc_audit_reality_boundary_reconcile_uses_request_and_provider_ids() -> None:
    signature = inspect.signature(RealityBoundary.reconcile)
    assert {"request_id", "provider_id"} <= set(signature.parameters)
    source = inspect.getsource(RealityBoundary.reconcile)
    assert "registry.get(provider_id)" in source
    assert "reconcile(request_id)" in source
    assert "RecoveryApplication" not in source


def test_rc_audit_provider_protocol_has_no_reconciliation_repeatability_contract() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconcile_repeat_safe" not in fields
    assert "reconciliation_idempotent" not in fields


def test_rc_audit_registry_can_replace_same_provider_id_with_new_object() -> None:
    registry = ProviderRegistry()
    first = _ReplacementProvider("v1")
    second = _ReplacementProvider("v2")
    registry.register(first)  # type: ignore[arg-type]
    assert registry.get(first.descriptor.id) is first
    registry.unregister(first.descriptor.id)
    registry.register(second)  # type: ignore[arg-type]
    assert registry.get(second.descriptor.id) is second
    assert first is not second


def test_rc_audit_recovery_application_has_provider_id_but_no_execution_binding() -> None:
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


def test_rc_audit_recovery_observation_has_no_first_class_application_binding() -> None:
    request_fields = set(RecoveryObservationCommitRequest.__dataclass_fields__)
    observation_fields = set(RecoveryObservation.__dataclass_fields__)
    assert "recovery_application_ref" not in request_fields
    assert "recovery_application_ref" not in observation_fields
    assert "provenance_refs" in request_fields
    assert "provenance_refs" in observation_fields


def test_rc_audit_runtime_creates_new_observation_instance_per_legacy_reconcile() -> None:
    source = inspect.getsource(Runtime.reconcile)
    assert 'new_id(\n                                "recovery_observation_instance"' in source
    assert "recovery_application_ref" not in source


def test_rc_audit_local_invocation_specification_is_not_reconciliation_authority() -> None:
    source = inspect.getsource(Runtime.reconcile)
    boundary_source = inspect.getsource(RealityBoundary.reconcile)
    assert "invocation_spec" not in source
    assert "invocation_spec" not in boundary_source


def test_rc_audit_no_reconciliation_consumption_production_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation") is None


@_xfail("B4 RC-001: Step/Attempt identity alone cannot authorize reconciliation consumption")
def test_rc_001_step_attempt_alone_is_not_consumption_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    with pytest.raises(ValueError, match="RecoveryApplication|application|authority"):
        module.prepare_reconciliation_consumption(
            store=None,
            request=module.ReconciliationConsumptionRequest(
                recovery_application_ref=None,
                step_ref="step:legacy",
                attempt_ref="attempt:legacy",
            ),
        )


@_xfail("B4 RC-002: RecoveryDisposition alone cannot authorize reconciliation consumption")
def test_rc_002_disposition_alone_is_not_consumption_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    with pytest.raises(ValueError, match="RecoveryApplication|application|authority"):
        module.prepare_reconciliation_consumption(
            store=None,
            request=module.ReconciliationConsumptionRequest(
                recovery_application_ref="recovery_disposition:not-an-application"
            ),
        )


@_xfail("B4 RC-003: exact reconciliation-request RecoveryApplication is the only positive trigger")
def test_rc_003_exact_reconciliation_application_is_required() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(application_kind="reconciliation-request")
    plan = fixture.prepare()
    assert plan.application_ref == fixture.application.id
    assert plan.application_kind == "reconciliation-request"
    assert plan.provider_calls == 0


@_xfail("B4 RC-004: non-reconciliation RecoveryApplication kinds cannot enter reconcile path")
def test_rc_004_wrong_application_kind_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    for kind in (
        "retry-request",
        "hold",
        "manual-resolution-handoff",
        "objective-resolution-acceptance",
    ):
        fixture = module.ReconciliationAuditFixture.example(application_kind=kind)
        with pytest.raises(ValueError, match="reconciliation-request|application kind|reconcile"):
            fixture.prepare()


@_xfail("B4 RC-005: source dispatch/Attempt/Action must be reconstructed from durable authority")
def test_rc_005_caller_source_fields_cannot_override_durable_application_graph() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fields = set(module.ReconciliationConsumptionRequest.__dataclass_fields__)
    assert fields == {"recovery_application_ref"}


@_xfail("B4 RC-006: provider-id equality is not authoritative reconciliation target identity")
def test_rc_006_provider_id_only_binding_is_ineligible() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(
        source_provider_id="provider:a",
        source_provider_binding=None,
    )
    eligibility = fixture.target_eligibility(current_provider_id="provider:a")
    assert eligibility.allowed is False
    assert "binding" in eligibility.reason.lower() or "identity" in eligibility.reason.lower()


@_xfail("B4 RC-007: registry replacement under same provider id cannot silently retarget reconciliation")
def test_rc_007_same_id_replacement_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    source = module.ReconciliationProviderBinding.example(
        provider_id="provider:a",
        binding_digest="binding:source",
    )
    current = module.ReconciliationProviderBinding.example(
        provider_id="provider:a",
        binding_digest="binding:replacement",
    )
    with pytest.raises(ValueError, match="binding|identity|replacement|drift"):
        module.assert_same_reconciliation_target(source, current)


@_xfail("B4 RC-008: legacy dispatch provider binding cannot be backfilled from current registry")
def test_rc_008_historical_provider_binding_backfill_is_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    with pytest.raises(ValueError, match="historical|binding|backfill|legacy"):
        module.reconciliation_binding_from_legacy_dispatch(
            dispatch_ref="dispatch:provider-id-only",
            provider_id="provider:a",
            current_registry_binding="binding:current",
        )


@_xfail("B4 RC-009: automatic reconciliation repeat requires explicit repeatability authority")
def test_rc_009_repeatability_must_be_explicit() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    eligibility = module.reconciliation_repeat_eligibility(
        repeatability_contract=None,
        external_call_may_have_started=True,
        bound_observation_exists=False,
    )
    assert eligibility.allowed is False
    assert "repeat" in eligibility.reason.lower() or "ambiguous" in eligibility.reason.lower()


@_xfail("B4 RC-010: post-call/pre-observation crash with unproven repeatability fails closed")
def test_rc_010_post_call_pre_observation_crash_is_ambiguous_without_repeat_safety() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    state = module.classify_reconciliation_crash(
        external_call_started=True,
        external_call_returned=True,
        durable_observation_ref=None,
        repeatability="unproven",
    )
    assert state.status == "ambiguous"
    assert state.auto_repeat_allowed is False


@_xfail("B4 RC-011: reconciliation RecoveryObservation needs first-class RecoveryApplication binding")
def test_rc_011_observation_schema_binds_exact_recovery_application() -> None:
    assert "recovery_application_ref" in RecoveryObservationCommitRequest.__dataclass_fields__
    assert "recovery_application_ref" in RecoveryObservation.__dataclass_fields__


@_xfail("B4 RC-012: one application with an existing bound observation must not call provider again")
def test_rc_012_existing_bound_observation_short_circuits_provider_call() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(
        application_kind="reconciliation-request",
        bound_observation_exists=True,
    )
    result = fixture.consume()
    assert result.replayed is True
    assert fixture.provider_calls == 0


@_xfail("B4 RC-013: a new RecoveryObservation does not auto-create disposition or application")
def test_rc_013_observation_commit_stops_before_new_decision_or_application() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(application_kind="reconciliation-request")
    fixture.consume_once()
    assert fixture.recovery_observations == 1
    assert fixture.new_recovery_dispositions == 0
    assert fixture.new_recovery_applications == 0


@_xfail("B4 RC-014: reconciliation result is execution observation, not Outcome or RecoveryDisposition")
def test_rc_014_reconciliation_result_cannot_promote_itself_to_objective_or_decision_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(application_kind="reconciliation-request")
    fixture.consume_once(provider_status="succeeded")
    assert fixture.recovery_observations == 1
    assert fixture.confirmed_outcomes == 0
    assert fixture.new_recovery_dispositions == 0


@_xfail("B4 RC-015: reconciliation consumption creates no fresh invocation execution authority")
def test_rc_015_reconciliation_creates_no_fresh_request_permit_attempt_dispatch_or_invoke() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_reconciliation")
    fixture = module.ReconciliationAuditFixture.example(application_kind="reconciliation-request")
    fixture.consume_once()
    assert fixture.fresh_capability_requests == 0
    assert fixture.invocation_permits == 0
    assert fixture.fresh_attempts == 0
    assert fixture.dispatch_commits == 0
    assert fixture.provider_invocations == 0
    assert fixture.reconcile_calls == 1


@_xfail("B4 RC-016: legacy Runtime.reconcile(step_id) cannot remain an authority bypass")
def test_rc_016_runtime_step_only_reconcile_is_fail_closed_without_application_authority() -> None:
    source = inspect.getsource(Runtime.reconcile)
    assert "RecoveryApplicationRequired" in source or "recovery_application" in source.lower()
    assert "self.capabilities.reconcile(last.request_ref, last.provider_id)" not in source
