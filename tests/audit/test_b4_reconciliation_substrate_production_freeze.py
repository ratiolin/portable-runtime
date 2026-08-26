"""Unified B4 reconciliation substrate production freeze.

A application-bound observation authority, B configured-provider execution
binding, and C exact reconciliation repeatability authority are supported
locally. Reconciliation consumer/provider calls, DIS-015, PVP-007, retry,
fresh invocation authority, and P5 authority remain closed.
"""

from __future__ import annotations

import importlib.util
import inspect
from typing import Any

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
from portable_runtime.core.provider_semantics import ProviderReplayBinding
from portable_runtime.core.reconciliation_repeatability import (
    ReconciliationRepeatabilityAuthority,
    ReconciliationRepeatabilityConfiguration,
    build_reconciliation_repeatability_authority,
    build_reconciliation_repeatability_contract,
    evaluate_reconciliation_repeatability,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.dispatch import DISPATCH_COMMIT_EVENT
from portable_runtime.governance.distinction import DistinctionState, UseContext
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    provider_execution_binding_from_dispatch,
    reject_historical_execution_binding_backfill,
)
from portable_runtime.governance.use_admission import GovernanceUseRequirement
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.recovery_application_observation import (
    RecoveryApplicationObservationInMemoryStateStore,
)
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
    application_observation_identity,
)
from portable_runtime.workflows.recovery_observation import (
    RECOVERY_OBSERVATION_EVENT,
    RecoveryObservation,
    RecoveryObservationCommitRequest,
)


def test_rsf_application_observation_binding_is_local_production() -> None:
    assert "recovery_application_ref" in RecoveryObservation.__dataclass_fields__
    assert "recovery_application_ref" not in RecoveryObservationCommitRequest.__dataclass_fields__
    assert set(RecoveryApplicationObservationCommitRequest.__dataclass_fields__) == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }


def test_rsf_current_provider_protocol_has_no_repeatability_authority() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]
    fields = set(ProviderDescriptor.model_fields)
    assert "reconciliation_repeatability" not in fields
    assert "reconciliation_repeatability_contract" not in fields


def test_rsf_v1_does_not_authorize_reconciliation_attempt_fact() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation_attempt") is None


def test_rsf_v1_does_not_authorize_generic_application_consumed_fact() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_application_consumed") is None


def test_rsf_local_provider_replay_binding_remains_non_authoritative_representation() -> None:
    doc = inspect.getdoc(ProviderReplayBinding) or ""
    assert "not proof" in doc.lower()
    assert "authoritative configured provider instance" in doc.lower()


def test_rsf_reconciliation_consumer_production_remains_absent() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation") is None


def test_rsf_001_bound_observation_requires_exact_application_authority() -> None:
    fields = set(RecoveryApplicationObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }


def test_rsf_002_one_application_one_completion_identity() -> None:
    first = application_observation_identity("recovery_application:a")
    second = application_observation_identity("recovery_application:a")
    assert first == second
    assert application_observation_identity("recovery_application:b") != first


def test_rsf_003_bound_observation_direct_append_and_import_are_closed() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    forged = Event(
        id="recovery_observation_forged_bound",
        type=RECOVERY_OBSERVATION_EVENT,
        subject_ref="recovery_application:forged",
        payload={"recovery_application_ref": "recovery_application:forged"},
    )
    with pytest.raises(ValueError, match="RecoveryObservation|commit"):
        store.append_event(forged)
    with pytest.raises(ValueError, match="import|P5|unsupported"):
        store.import_state({"event": [forged.model_dump(mode="json")]})


class _BindingProvider:
    def __init__(self, store: InMemoryStateStore | None = None) -> None:
        self.store = store
        self.calls = 0
        self.descriptor = ProviderDescriptor(
            id="provider:rsf-b",
            name="RSF B provider",
            version="1",
            capabilities=["test.read"],
            effect_semantics="pure",
            side_effect_class="pure",
            reversibility="reversible",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        del context
        self.calls += 1
        if self.store is not None:
            dispatches = [
                event
                for event in self.store.list_events()
                if event.type == DISPATCH_COMMIT_EVENT and event.subject_ref == request.id
            ]
            assert len(dispatches) == 1
            assert "provider_execution_binding_ref" in dispatches[0].payload
            provider_execution_binding_from_dispatch(dispatches[0])
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        del request_id
        raise AssertionError("reconciliation consumer is not authorized")


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a"}),
        partition=(frozenset({"a"}),),
        version=1,
    )


def _requirement(_request: CapabilityRequest) -> GovernanceUseRequirement:
    return GovernanceUseRequirement(
        scheme_id="d",
        use_context=UseContext("ctx", frozenset({"a"})),
    )


def _repeatability(
    *,
    mode: str = "repeat-safe",
    protocol_version: str = "1",
    contract_version: str = "1",
) -> ReconciliationRepeatabilityConfiguration:
    return ReconciliationRepeatabilityConfiguration(
        reconciliation_protocol_identity="capability-provider.reconcile",
        reconciliation_protocol_version=protocol_version,
        repeatability_mode=mode,
        contract_version=contract_version,
    )


def _register(
    registry: ProviderRegistry,
    provider: _BindingProvider,
    suffix: str,
    *,
    repeatability: ReconciliationRepeatabilityConfiguration | None = None,
) -> None:
    registry.register(
        provider,
        configured_execution_identity=f"configured:rsf:{suffix}",
        authoritative_configuration_ref=f"provider-config:rsf:{suffix}",
        reconciliation_repeatability=repeatability,
    )


def test_rsf_004_execution_binding_has_registry_authoritative_origin() -> None:
    registry = ProviderRegistry()
    provider = _BindingProvider()
    _register(registry, provider, "004")
    captured, binding = registry.capture_execution_target(
        provider.descriptor.id,
        expected_provider=provider,
    )
    assert captured is provider
    assert binding.configured_execution_identity == "configured:rsf:004"
    assert binding.authoritative_configuration_ref == "provider-config:rsf:004"


async def test_rsf_005_binding_is_durable_before_provider_reality_exit() -> None:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    provider = _BindingProvider(store)
    registry = ProviderRegistry()
    _register(registry, provider, "005")
    boundary = RealityBoundary(
        store=store,
        registry=registry,
        governance_requirement_resolver=_requirement,
    )
    request = CapabilityRequest(
        id="request:rsf:005",
        capability="test.read",
        idempotency_key="idem:rsf:005",
    )
    result = await boundary.execute(request)
    assert result.status == "succeeded"
    assert provider.calls == 1


def test_rsf_006_same_id_replacement_fails_exact_target_resolution() -> None:
    registry = ProviderRegistry()
    source = _BindingProvider()
    _register(registry, source, "006-source")
    historical = registry.execution_binding(source.descriptor.id, expected_provider=source)
    registry.unregister(source.descriptor.id)
    replacement = _BindingProvider()
    _register(registry, replacement, "006-replacement")
    assert registry.resolve_execution_binding(historical) is None


def test_rsf_007_legacy_execution_binding_backfill_is_closed() -> None:
    with pytest.raises(ValueError, match="historical|backfill|unsupported"):
        reject_historical_execution_binding_backfill(
            "dispatch:legacy",
            "provider:rsf-b",
            "provider-config:current",
        )


def test_rsf_008_repeatability_authority_has_exact_b_subject_protocol_domain() -> None:
    fields = set(ReconciliationRepeatabilityAuthority.model_fields)
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


def test_rsf_009_repeatability_authority_cannot_float_free_of_exact_b() -> None:
    first_registry = ProviderRegistry()
    first_provider = _BindingProvider()
    _register(first_registry, first_provider, "009-first", repeatability=_repeatability())
    first_binding = first_registry.execution_binding(first_provider.descriptor.id)
    first_contract = first_registry.reconciliation_repeatability_contract(
        first_provider.descriptor.id
    )
    assert first_contract is not None

    second_registry = ProviderRegistry()
    second_provider = _BindingProvider()
    _register(second_registry, second_provider, "009-second", repeatability=_repeatability())
    second_binding = second_registry.execution_binding(second_provider.descriptor.id)
    second_contract = second_registry.reconciliation_repeatability_contract(
        second_provider.descriptor.id
    )
    assert second_contract is not None

    assert first_binding.provider_id == second_binding.provider_id
    assert first_binding.id != second_binding.id
    assert first_contract.provider_execution_binding_ref == first_binding.id
    assert second_contract.provider_execution_binding_ref == second_binding.id
    assert first_contract.id != second_contract.id


def test_rsf_010_absent_unknown_or_drifted_repeatability_is_ineligible() -> None:
    registry = ProviderRegistry()
    provider = _BindingProvider()
    _register(registry, provider, "010", repeatability=_repeatability())
    binding = registry.execution_binding(provider.descriptor.id)
    contract = registry.reconciliation_repeatability_contract(provider.descriptor.id)
    assert contract is not None
    authority = build_reconciliation_repeatability_authority(
        contract,
        subject_identity="request:rsf:010",
    )

    absent = evaluate_reconciliation_repeatability(
        None,
        historical_binding=binding,
        current_contract=contract,
        required_subject_identity="request:rsf:010",
    )
    assert absent.eligible is False

    unknown_contract = build_reconciliation_repeatability_contract(
        binding,
        _repeatability(mode="unknown"),
    )
    unknown = evaluate_reconciliation_repeatability(
        authority,
        historical_binding=binding,
        current_contract=unknown_contract,
        required_subject_identity="request:rsf:010",
    )
    assert unknown.eligible is False

    drifted_contract = build_reconciliation_repeatability_contract(
        binding,
        _repeatability(contract_version="2"),
    )
    drifted = evaluate_reconciliation_repeatability(
        authority,
        historical_binding=binding,
        current_contract=drifted_contract,
        required_subject_identity="request:rsf:010",
    )
    assert drifted.eligible is False


def test_rsf_011_v1_positive_authority_is_repeat_safe_only() -> None:
    for mode, expected in (
        ("repeat-safe", True),
        ("unknown", False),
        ("non-repeat-safe", False),
    ):
        registry = ProviderRegistry()
        provider = _BindingProvider()
        _register(
            registry,
            provider,
            f"011-{mode}",
            repeatability=_repeatability(mode=mode),
        )
        _provider, _binding_value, authority = registry.capture_reconciliation_execution_target(
            provider.descriptor.id,
            subject_identity=f"request:rsf:011:{mode}",
            expected_provider=provider,
        )
        assert (authority is not None) is expected


def test_rsf_012_all_required_substrate_authorities_remain_non_executing() -> None:
    for obj in (
        RecoveryApplicationObservationCommitRequest,
        ProviderExecutionBinding,
        ReconciliationRepeatabilityAuthority,
    ):
        assert not hasattr(obj, "invoke")
        assert not hasattr(obj, "reconcile")
        assert not hasattr(obj, "retry")
        assert not hasattr(obj, "materialize_capability_request")
