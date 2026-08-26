"""Unified B4 reconciliation substrate production decision freeze.

Audit/freeze only. No substrate production, reconciliation consumer, provider
call, DIS-015, PVP-007, retry, fresh invocation authority, or P5 authority is
authorized by this file.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.capabilities import ProviderDescriptor
from portable_runtime.core.provider_semantics import ProviderReplayBinding
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservation,
    RecoveryObservationCommitRequest,
)


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_rsf_current_observation_has_no_application_binding_production() -> None:
    assert "recovery_application_ref" not in RecoveryObservation.__dataclass_fields__
    assert "recovery_application_ref" not in RecoveryObservationCommitRequest.__dataclass_fields__


def test_rsf_current_provider_protocol_has_no_repeatability_authority() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_repeatability_contract" not in fields


def test_rsf_current_provider_execution_binding_module_is_absent() -> None:
    assert importlib.util.find_spec("portable_runtime.governance.provider_execution_binding") is None


def test_rsf_v1_does_not_authorize_reconciliation_attempt_fact() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation_attempt") is None


def test_rsf_v1_does_not_authorize_generic_application_consumed_fact() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_application_consumed") is None


def test_rsf_current_dispatch_has_no_configured_execution_binding() -> None:
    source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "provider_execution_binding" not in source
    assert "configured_execution_identity" not in source


def test_rsf_local_provider_replay_binding_remains_non_authoritative_representation() -> None:
    doc = inspect.getdoc(ProviderReplayBinding) or ""
    assert "not proof" in doc.lower()
    assert "authoritative configured provider instance" in doc.lower()


def test_rsf_reconciliation_consumer_production_remains_absent() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation") is None


@_xfail("B4 RSF-001: application-bound observation requires exact RecoveryApplication authority")
def test_rsf_001_bound_observation_requires_exact_application_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation_binding")
    fields = set(module.RecoveryApplicationObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }


@_xfail("B4 RSF-002: one application derives one deterministic completion observation identity")
def test_rsf_002_one_application_one_completion_identity() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation_binding")
    first = module.bound_observation_identity("recovery_application:a")
    second = module.bound_observation_identity("recovery_application:a")
    assert first == second
    assert module.bound_observation_identity("recovery_application:b") != first


@_xfail("B4 RSF-003: bound observation direct append/import authority remains closed")
def test_rsf_003_bound_observation_direct_append_and_import_are_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation_binding")
    fixture = module.BoundObservationAuditFixture.example()
    with pytest.raises(ValueError, match="direct|authority|append"):
        fixture.direct_append()
    with pytest.raises(ValueError, match="import|serialized|P5|unsupported"):
        fixture.import_serialized_authority()


@_xfail("B4 RSF-004: configured-provider binding originates from authoritative provider path")
def test_rsf_004_execution_binding_has_authoritative_origin() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    fixture = module.ProviderExecutionBindingAuditFixture.example()
    binding = fixture.capture_from_authoritative_selection()
    assert binding.authoritative_configuration_ref == fixture.configuration_ref


@_xfail("B4 RSF-005: execution binding capture precedes or linearizes with reality-exit authorization")
def test_rsf_005_execution_binding_is_durable_before_reality_exit_can_be_ambiguous() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    plan = module.ProviderExecutionBindingAuditFixture.example().capture_plan()
    assert plan.binding_durable_before_provider_call is True
    assert plan.provider_call_before_binding_commit is False


@_xfail("B4 RSF-006: same-id provider replacement cannot satisfy historical execution binding")
def test_rsf_006_same_id_replacement_fails_exact_target_resolution() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    source = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:source",
    )
    replacement = module.ProviderExecutionBinding.example(
        provider_id="provider:a",
        configured_execution_identity="configured:replacement",
    )
    result = module.resolve_historical_reconciliation_target(source, replacement)
    assert result.allowed is False


@_xfail("B4 RSF-007: legacy configured-provider execution binding backfill remains closed")
def test_rsf_007_legacy_execution_binding_backfill_is_closed() -> None:
    module = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    with pytest.raises(ValueError, match="historical|legacy|backfill|unsupported"):
        module.backfill_historical_execution_binding(
            dispatch_ref="dispatch:legacy",
            provider_id="provider:a",
            current_configuration_ref="provider-config:current",
        )


@_xfail("B4 RSF-008: repeatability authority binds exact subject/provider execution/protocol/version")
def test_rsf_008_repeatability_contract_has_exact_authority_domain() -> None:
    module = importlib.import_module("portable_runtime.core.reconciliation_repeatability")
    fields = set(module.ReconciliationRepeatabilityContract.model_fields)
    assert {
        "subject_model",
        "subject_identity",
        "provider_execution_binding_ref",
        "reconciliation_protocol_identity",
        "reconciliation_protocol_version",
        "contract_version",
        "contract_digest",
        "repeatability_mode",
    } <= fields


@_xfail("B4 RSF-009: repeatability authority binds exact configured-provider execution binding")
def test_rsf_009_repeatability_contract_cannot_float_free_of_execution_binding() -> None:
    module = importlib.import_module("portable_runtime.core.reconciliation_repeatability")
    with pytest.raises(ValueError, match="provider.*execution.*binding|target|identity"):
        module.ReconciliationRepeatabilityContract.example(
            provider_execution_binding_ref=None,
            repeatability_mode="repeat-safe",
        )


@_xfail("B4 RSF-010: absent, unknown, or drifted repeatability fails closed")
def test_rsf_010_unknown_or_drifted_repeatability_is_ineligible() -> None:
    module = importlib.import_module("portable_runtime.core.reconciliation_repeatability")
    for mode in (None, "unknown", "non-repeat-safe", "drifted"):
        eligibility = module.v1_reconciliation_repeat_eligibility(mode)
        assert eligibility.allowed is False


@_xfail("B4 RSF-011: v1 automatic reconciliation accepts only exact repeat-safe authority")
def test_rsf_011_v1_is_repeat_safe_only() -> None:
    module = importlib.import_module("portable_runtime.core.reconciliation_repeatability")
    safe = module.v1_reconciliation_repeat_eligibility("repeat-safe")
    assert safe.allowed is True
    for mode in ("unknown", "non-repeat-safe"):
        assert module.v1_reconciliation_repeat_eligibility(mode).allowed is False


@_xfail("B4 RSF-012: all required substrate authorities remain non-executing by themselves")
def test_rsf_012_substrate_objects_do_not_own_execution() -> None:
    observation = importlib.import_module("portable_runtime.workflows.recovery_observation_binding")
    target = importlib.import_module("portable_runtime.governance.provider_execution_binding")
    repeatability = importlib.import_module("portable_runtime.core.reconciliation_repeatability")
    for obj in (
        observation.BoundRecoveryObservationAuthority,
        target.ProviderExecutionBinding,
        repeatability.ReconciliationRepeatabilityContract,
    ):
        assert not hasattr(obj, "invoke")
        assert not hasattr(obj, "reconcile")
        assert not hasattr(obj, "retry")
        assert not hasattr(obj, "materialize_capability_request")
