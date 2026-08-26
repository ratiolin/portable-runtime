"""B4 reconciliation repeatability production graduation.

C is supported only as registry-configured, exact-B, exact-request-id historical
repeatability authority. This file does not authorize a reconciliation consumer,
provider call, retry, fresh invocation authority, DIS-015/PVP-007, or P5 import.
"""

from __future__ import annotations

import inspect

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import Event
from portable_runtime.core.reconciliation_repeatability import (
    ReconciliationRepeatabilityAuthority,
    ReconciliationRepeatabilityConfiguration,
    build_reconciliation_repeatability_authority,
    build_reconciliation_repeatability_contract,
    evaluate_reconciliation_repeatability,
    reconciliation_repeatability_authority_from_dispatch,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    build_provider_execution_binding,
)
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.workflows.recovery_application import RecoveryApplication
from portable_runtime.workflows.recovery_observation import RecoveryObservation


class _Provider:
    def __init__(self, *, effect_semantics: str = "reconcilable") -> None:
        self.descriptor = ProviderDescriptor(
            id="provider:rr",
            name="rr",
            version="1",
            capabilities=["deploy.apply"],
            effect_semantics=effect_semantics,
            side_effect_class=effect_semantics,
            reversibility="unknown" if effect_semantics == "reconcilable" else "reversible",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        del context
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        del request_id
        raise AssertionError("repeatability authority alone cannot call reconcile")


def _configuration(
    *,
    protocol_version: str = "1",
    contract_version: str = "1",
    repeatability_mode: str = "repeat-safe",
) -> ReconciliationRepeatabilityConfiguration:
    return ReconciliationRepeatabilityConfiguration(
        reconciliation_protocol_identity="capability-provider.reconcile",
        reconciliation_protocol_version=protocol_version,
        repeatability_mode=repeatability_mode,
        contract_version=contract_version,
    )


def _binding(suffix: str) -> ProviderExecutionBinding:
    provider = _Provider()
    return build_provider_execution_binding(
        provider.descriptor,
        configured_execution_identity=f"configured:rr:{suffix}",
        authoritative_configuration_ref=f"provider-config:rr:{suffix}",
    )


def _authority(
    suffix: str = "authority",
    *,
    subject_identity: str = "request:rr",
    protocol_version: str = "1",
    contract_version: str = "1",
) -> tuple[ProviderExecutionBinding, object, ReconciliationRepeatabilityAuthority]:
    binding = _binding(suffix)
    contract = build_reconciliation_repeatability_contract(
        binding,
        _configuration(
            protocol_version=protocol_version,
            contract_version=contract_version,
        ),
    )
    authority = build_reconciliation_repeatability_authority(
        contract,
        subject_identity=subject_identity,
    )
    return binding, contract, authority


def test_rr_provider_reconcile_contract_remains_request_id_only() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]


def test_rr_provider_descriptor_still_has_no_repeatability_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_subject_model" not in fields
    assert "reconciliation_contract_version" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_business_effect_semantics_remain_separate_from_reconciliation() -> None:
    annotation = ProviderDescriptor.model_fields["effect_semantics"].annotation
    assert annotation is not None
    assert "reconcil" in str(annotation)
    assert "repeat" not in str(annotation).lower()


def test_rr_capability_result_does_not_carry_repeatability_proof() -> None:
    fields = set(CapabilityResult.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields
    assert {"external_operation_ref", "reconciled"} <= fields


def test_rr_reality_boundary_still_has_no_repeatability_consumer_gate() -> None:
    signature = inspect.signature(RealityBoundary.reconcile)
    assert {"request_id", "provider_id"} <= set(signature.parameters)
    source = inspect.getsource(RealityBoundary.reconcile)
    assert "reconcile(request_id)" in source
    assert "repeatability" not in source.lower()


def test_rr_recovery_application_does_not_claim_repeatability() -> None:
    fields = set(RecoveryApplication.__dataclass_fields__)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_recovery_observation_does_not_claim_repeatability() -> None:
    fields = set(RecoveryObservation.__dataclass_fields__)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_contract_digest" not in fields


def test_rr_001_absence_of_explicit_historical_authority_is_ineligible() -> None:
    binding = _binding("rr001")
    result = evaluate_reconciliation_repeatability(
        None,
        historical_binding=binding,
        current_contract=None,
        required_subject_identity="request:rr001",
    )
    assert result.status == "ineligible"
    assert result.eligible is False


def test_rr_002_method_name_reconcile_does_not_create_repeatability_authority() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    registry.register(
        provider,
        configured_execution_identity="configured:rr:002",
        authoritative_configuration_ref="provider-config:rr:002",
    )
    assert registry.reconciliation_repeatability_contract(provider.descriptor.id) is None
    _provider, _binding_value, authority = registry.capture_reconciliation_execution_target(
        provider.descriptor.id,
        subject_identity="request:rr002",
        expected_provider=provider,
    )
    assert authority is None


@pytest.mark.parametrize("effect_semantics", ["idempotent", "reconcilable"])
def test_rr_003_business_idempotency_is_not_reconciliation_repeatability(
    effect_semantics: str,
) -> None:
    registry = ProviderRegistry()
    provider = _Provider(effect_semantics=effect_semantics)
    registry.register(
        provider,
        configured_execution_identity=f"configured:rr:003:{effect_semantics}",
        authoritative_configuration_ref=f"provider-config:rr:003:{effect_semantics}",
    )
    assert registry.reconciliation_repeatability_contract(provider.descriptor.id) is None


def test_rr_004_provider_id_equality_is_not_repeatability_authority() -> None:
    first = _binding("first")
    second = _binding("second")
    assert first.provider_id == second.provider_id
    assert first.id != second.id
    first_contract = build_reconciliation_repeatability_contract(first, _configuration())
    second_contract = build_reconciliation_repeatability_contract(second, _configuration())
    assert first_contract.id != second_contract.id


def test_rr_005_contract_or_protocol_drift_invalidates_historical_authority() -> None:
    binding, historical_contract, authority = _authority(
        "rr005",
        subject_identity="request:rr005",
        contract_version="1",
    )
    current_contract = build_reconciliation_repeatability_contract(
        binding,
        _configuration(contract_version="2"),
    )
    assert current_contract.contract_digest != historical_contract.contract_digest
    result = evaluate_reconciliation_repeatability(
        authority,
        historical_binding=binding,
        current_contract=current_contract,
        required_subject_identity="request:rr005",
    )
    assert result.eligible is False
    assert "drift" in result.reason.lower()


def test_rr_006_post_call_repeat_requires_exact_repeat_safe_authority() -> None:
    binding, contract, authority = _authority(
        "rr006",
        subject_identity="request:rr006",
    )
    exact = evaluate_reconciliation_repeatability(
        authority,
        historical_binding=binding,
        current_contract=contract,
        required_subject_identity="request:rr006",
    )
    missing = evaluate_reconciliation_repeatability(
        None,
        historical_binding=binding,
        current_contract=contract,
        required_subject_identity="request:rr006",
    )
    assert exact.eligible is True
    assert missing.eligible is False


def test_rr_007_unknown_repeatability_fails_closed() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    registry.register(
        provider,
        configured_execution_identity="configured:rr:007",
        authoritative_configuration_ref="provider-config:rr:007",
        reconciliation_repeatability=_configuration(repeatability_mode="unknown"),
    )
    _provider, binding, authority = registry.capture_reconciliation_execution_target(
        provider.descriptor.id,
        subject_identity="request:rr007",
        expected_provider=provider,
    )
    assert authority is None
    contract = registry.reconciliation_repeatability_contract(provider.descriptor.id)
    assert contract is not None
    result = evaluate_reconciliation_repeatability(
        authority,
        historical_binding=binding,
        current_contract=contract,
        required_subject_identity="request:rr007",
    )
    assert result.eligible is False


def test_rr_008_repeatability_authority_does_not_authorize_provider_invoke() -> None:
    _binding_value, _contract, authority = _authority("rr008")
    assert not hasattr(authority, "invoke")
    assert not hasattr(type(authority), "invoke")
    assert "provider.invoke" not in repr(authority)


def test_rr_009_repeatability_authority_does_not_authorize_retry() -> None:
    _binding_value, _contract, authority = _authority("rr009")
    assert not hasattr(authority, "retry")
    assert not hasattr(authority, "materialize_capability_request")


def test_rr_010_repeatability_authority_cannot_override_bound_observation_completion() -> None:
    fields = set(ReconciliationRepeatabilityAuthority.model_fields)
    assert "recovery_application_ref" not in fields
    assert "recovery_observation_ref" not in fields
    assert "recovery_application_ref" in RecoveryObservation.__dataclass_fields__
    assert not hasattr(ReconciliationRepeatabilityAuthority, "reopen")
    assert not hasattr(ReconciliationRepeatabilityAuthority, "consume")


def test_rr_011_caller_cannot_declare_repeat_safe_ad_hoc() -> None:
    signature = inspect.signature(ProviderRegistry.register)
    assert "repeat_safe" not in signature.parameters
    assert "contract_digest" not in ReconciliationRepeatabilityConfiguration.model_fields
    configuration = _configuration()
    assert not isinstance(configuration, ReconciliationRepeatabilityAuthority)


def test_rr_012_legacy_or_b_only_history_cannot_be_backfilled_from_current_contract() -> None:
    binding = _binding("rr012")
    event = Event(
        id="dispatch:rr012",
        type="InvocationDispatchCommitted",
        subject_ref="request:rr012",
        payload={
            "request_id": "request:rr012",
            "provider_id": binding.provider_id,
            "provider_execution_binding_ref": binding.id,
            "provider_execution_binding": binding.model_dump(mode="json"),
        },
    )
    with pytest.raises(ValueError, match="historical|backfill|unsupported"):
        reconciliation_repeatability_authority_from_dispatch(event)
