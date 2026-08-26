"""B4 reconciliation repeatability audit.

Audit only. This file authorizes no repeatability production, provider protocol
change, configured-provider target binding, RecoveryObservation binding
production, Runtime consumption, reconciliation provider call, retry, fresh
invocation authority, DIS-015/PVP-007, or P5 import authority.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import CapabilityResult, ProviderDescriptor
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.workflows.recovery_application import RecoveryApplication
from portable_runtime.workflows.recovery_observation import RecoveryObservation


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_rr_audit_provider_reconcile_contract_is_request_id_only() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]


def test_rr_audit_provider_descriptor_has_no_repeatability_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_subject_model" not in fields
    assert "reconciliation_contract_version" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_audit_business_effect_semantics_are_separate_from_reconciliation() -> None:
    annotation = ProviderDescriptor.model_fields["effect_semantics"].annotation
    assert annotation is not None
    assert "reconcil" in str(annotation)
    assert "repeat" not in str(annotation).lower()


def test_rr_audit_capability_result_does_not_carry_repeatability_proof() -> None:
    fields = set(CapabilityResult.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields
    assert {"external_operation_ref", "reconciled"} <= fields


def test_rr_audit_reality_boundary_has_no_repeatability_gate() -> None:
    signature = inspect.signature(RealityBoundary.reconcile)
    assert {"request_id", "provider_id"} <= set(signature.parameters)
    source = inspect.getsource(RealityBoundary.reconcile)
    assert "reconcile(request_id)" in source
    assert "repeat" not in source.lower()
    assert "contract" not in source.lower()


def test_rr_audit_recovery_application_does_not_claim_repeatability() -> None:
    fields = set(RecoveryApplication.__dataclass_fields__)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_audit_recovery_observation_does_not_claim_repeatability() -> None:
    fields = set(RecoveryObservation.__dataclass_fields__)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_audit_no_repeatability_production_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.reconciliation_repeatability") is None


@_xfail("B4 RR-001: absence of an explicit reconciliation contract must never imply repeat-safe")
def test_rr_001_absence_of_contract_is_not_repeat_safe() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    with pytest.raises(ValueError, match="contract|repeat|unknown"):
        module.evaluate_reconciliation_repeatability(None)


@_xfail("B4 RR-002: the method name reconcile does not prove observational purity or repeat safety")
def test_rr_002_method_name_does_not_prove_repeat_safety() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    with pytest.raises(ValueError, match="proof|contract|repeat"):
        module.ReconciliationRepeatabilityContract.from_method_name("reconcile")


@_xfail("B4 RR-003: business-operation idempotency is not reconciliation repeatability authority")
def test_rr_003_business_idempotency_is_not_reconciliation_repeatability() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    descriptor = ProviderDescriptor(
        id="provider:rr",
        name="rr",
        version="1",
        capabilities=["deploy.apply"],
        effect_semantics="idempotent",
        side_effect_class="idempotent",
    )
    with pytest.raises(ValueError, match="reconciliation|repeat"):
        module.contract_from_effect_semantics(descriptor)


@_xfail("B4 RR-004: provider_id equality is not repeatability authority")
def test_rr_004_provider_id_is_not_repeatability_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    with pytest.raises(ValueError, match="provider.*identity|contract"):
        module.ReconciliationRepeatabilityContract(
            provider_id="provider:rr",
            repeatability_mode="repeat-safe",
        )


@_xfail("B4 RR-005: contract/version drift cannot substitute current repeatability proof for historical proof")
def test_rr_005_contract_drift_invalidates_current_proof_substitution() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    old = module.ReconciliationRepeatabilityContract(
        subject_model="historical-dispatch",
        repeatability_mode="repeat-safe-query",
        provider_execution_identity="provider-binding:v1",
        protocol_identity="reconcile-protocol",
        contract_version="1",
        contract_digest="digest:v1",
    )
    current = module.ReconciliationRepeatabilityContract(
        subject_model="historical-dispatch",
        repeatability_mode="repeat-safe-query",
        provider_execution_identity="provider-binding:v1",
        protocol_identity="reconcile-protocol",
        contract_version="2",
        contract_digest="digest:v2",
    )
    assert not module.same_repeatability_authority(old, current)


@_xfail("B4 RR-006: post-call/pre-observation repetition requires exact explicit repeat-safe proof")
def test_rr_006_post_call_repeat_requires_exact_proof() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    with pytest.raises(ValueError, match="repeat|proof|ambiguous"):
        module.reconciliation_reentry_allowed(
            crash_state="post-call-pre-observation",
            contract=None,
        )


@_xfail("B4 RR-007: unknown reconciliation repeatability must fail closed")
def test_rr_007_unknown_repeatability_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    contract = module.ReconciliationRepeatabilityContract(
        subject_model="historical-dispatch",
        repeatability_mode="unknown",
        provider_execution_identity="provider-binding:v1",
        protocol_identity="reconcile-protocol",
        contract_version="1",
        contract_digest="digest:unknown",
    )
    assert module.reconciliation_reentry_allowed(
        crash_state="post-call-pre-observation",
        contract=contract,
    ) is False


@_xfail("B4 RR-008: repeatability proof may authorize only repeated reconciliation query, never provider.invoke")
def test_rr_008_repeatability_does_not_authorize_provider_invoke() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    contract = module.ReconciliationRepeatabilityContract(
        subject_model="historical-dispatch",
        repeatability_mode="repeat-safe-query",
        provider_execution_identity="provider-binding:v1",
        protocol_identity="reconcile-protocol",
        contract_version="1",
        contract_digest="digest:v1",
    )
    assert module.authorized_operations(contract) == frozenset({"provider.reconcile"})


@_xfail("B4 RR-009: reconciliation repeatability proof must not authorize business retry")
def test_rr_009_repeatability_does_not_authorize_retry() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    contract = module.ReconciliationRepeatabilityContract(
        subject_model="historical-dispatch",
        repeatability_mode="repeat-safe-query",
        provider_execution_identity="provider-binding:v1",
        protocol_identity="reconcile-protocol",
        contract_version="1",
        contract_digest="digest:v1",
    )
    assert module.retry_authorized(contract) is False


@_xfail("B4 RR-010: durable bound observation terminates the same application responsibility regardless of repeat-safe proof")
def test_rr_010_bound_observation_stops_same_application_reality_calls() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    assert module.reconciliation_reentry_allowed(
        crash_state="observation-durable",
        contract=None,
    ) is False


@_xfail("B4 RR-011: caller cannot manufacture repeat-safe authority ad hoc")
def test_rr_011_caller_cannot_declare_repeat_safe_ad_hoc() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    signature = inspect.signature(module.ReconciliationRepeatabilityCommitRequest)
    forbidden = {
        "repeat_safe",
        "repeatability_mode",
        "contract_digest",
        "provider_execution_identity",
    }
    assert forbidden.isdisjoint(signature.parameters)


@_xfail("B4 RR-012: legacy history cannot be backfilled with current repeatability authority")
def test_rr_012_legacy_history_cannot_be_backfilled_from_current_contract() -> None:
    module = importlib.import_module("portable_runtime.workflows.reconciliation_repeatability")
    with pytest.raises(ValueError, match="historical|backfill|authority"):
        module.bind_current_contract_to_legacy_dispatch(
            dispatch_ref="dispatch:legacy",
            current_contract_ref="repeatability-contract:current",
        )
