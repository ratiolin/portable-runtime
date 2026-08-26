"""B4 configured-provider execution-binding production graduation.

PT-001…017 are no longer design fixtures. They exercise the real
ProviderRegistry, governed dispatch, store authority fence, legacy compatibility,
and historical target resolution APIs. This file authorizes no reconciliation
repeatability, consumer, provider call, retry, DIS-015, PVP-007, or historical
backfill.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import Event
from portable_runtime.core.provider_semantics import ProviderReplayBinding
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.dispatch import (
    DISPATCH_COMMIT_EVENT,
    DISPATCH_COMMIT_SCHEMA,
    GovernanceDispatchCommitter,
    dispatch_commit_identity_from_payload,
)
from portable_runtime.governance.distinction import DistinctionState, UseContext
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    classify_historical_target_capture,
    provider_execution_binding_from_dispatch,
    reject_historical_execution_binding_backfill,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.invocation_specification import InvocationSpecificationCommitRequest


class _Provider:
    def __init__(self, marker: str = "v1") -> None:
        self._descriptor = ProviderDescriptor(
            id="provider:target-production",
            name="target-production",
            version=marker,
            capabilities=["test.read"],
            effect_semantics="pure",
            side_effect_class="pure",
            reversibility="reversible",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def drift(self) -> None:
        self._descriptor = self._descriptor.model_copy(update={"version": "drifted"})

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
        raise AssertionError("B binding is non-executing")


def _register(
    registry: ProviderRegistry,
    provider: _Provider,
    suffix: str,
) -> ProviderExecutionBinding:
    registry.register(
        provider,
        configured_execution_identity=f"configured:target:{suffix}",
        authoritative_configuration_ref=f"provider-config:target:{suffix}",
    )
    return registry.execution_binding(provider.descriptor.id, expected_provider=provider)


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


def _bound_dispatch(suffix: str) -> tuple[InMemoryStateStore, ProviderRegistry, _Provider, Event]:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    provider = _Provider()
    registry = ProviderRegistry()
    binding = _register(registry, provider, suffix)
    request = CapabilityRequest(
        id=f"request:pt:{suffix}",
        capability="test.read",
        idempotency_key=f"idem:pt:{suffix}",
    )
    admission = GovernanceUseAdmission(store).evaluate(request, _requirement)
    assert admission.status == "allowed"
    assert admission.requirement_digest is not None
    assert admission.snapshot_digest is not None
    permit = InvocationPermit.issue(
        request,
        provider_id=provider.descriptor.id,
        qualification_digest="",
        lease_generation=0,
        governance_applicable=True,
        governance_requirement_digest=admission.requirement_digest,
        governance_snapshot_digest=admission.snapshot_digest,
    )
    decision = GovernanceDispatchCommitter(store).commit(
        request,
        permit,
        _requirement,
        attempt_id=None,
        provider_registry=registry,
        expected_provider=provider,
    )
    assert decision.status == "committed"
    assert decision.commit_ref is not None
    assert decision.provider_execution_binding_ref == binding.id
    event = store.get_event(decision.commit_ref)
    assert event is not None
    return store, registry, provider, event


def _legacy_dispatch() -> Event:
    payload = {
        "schema": DISPATCH_COMMIT_SCHEMA,
        "request_id": "request:pt:legacy",
        "provider_id": "provider:target-production",
        "attempt_ref": None,
        "invocation_permit_digest": "permit:legacy",
        "qualification_digest": "",
        "governance_requirement_digest": "requirement:legacy",
        "governance_snapshot_digest": "snapshot:legacy",
        "lease_generation": 0,
        "linearization_domain": "authoritative-state-store",
    }
    return Event(
        id=dispatch_commit_identity_from_payload(payload),
        type=DISPATCH_COMMIT_EVENT,
        subject_ref="request:pt:legacy",
        payload=payload,
    )


def test_pt_001_provider_id_is_not_configured_execution_identity() -> None:
    provider = _Provider()
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="stronger than provider id"):
        registry.register(
            provider,
            configured_execution_identity=provider.descriptor.id,
            authoritative_configuration_ref="provider-config:pt:001",
        )


def test_pt_002_current_registry_state_cannot_backfill_legacy_dispatch() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    _register(registry, provider, "002")
    with pytest.raises(ValueError, match="legacy|backfill"):
        provider_execution_binding_from_dispatch(_legacy_dispatch())


def test_pt_003_same_id_replacement_does_not_resolve_historical_binding() -> None:
    registry = ProviderRegistry()
    first = _Provider("v1")
    historical = _register(registry, first, "first")
    registry.unregister(first.descriptor.id)
    replacement = _Provider("v2")
    _register(registry, replacement, "replacement")
    assert registry.resolve_execution_binding(historical) is None


def test_pt_004_descriptor_equality_does_not_create_same_execution_identity() -> None:
    first_registry = ProviderRegistry()
    second_registry = ProviderRegistry()
    first = _Provider("same")
    second = _Provider("same")
    first_registry.register(first)
    second_registry.register(second)
    assert first.descriptor == second.descriptor
    assert first_registry.execution_binding(first.descriptor.id) != second_registry.execution_binding(
        second.descriptor.id
    )


def test_pt_005_provider_replay_binding_remains_representation_not_execution_authority() -> None:
    fields = set(ProviderReplayBinding.model_fields)
    assert "provider_binding_id" in fields
    assert "configured_execution_identity" not in fields
    assert "authoritative_configuration_ref" not in fields
    doc = ProviderReplayBinding.__doc__ or ""
    assert "not proof" in doc.lower()


def test_pt_006_direct_binding_bearing_dispatch_append_is_rejected() -> None:
    _source, registry, provider, source_event = _bound_dispatch("006")
    binding = registry.execution_binding(provider.descriptor.id, expected_provider=provider)
    payload = dict(source_event.payload)
    payload["request_id"] = "request:pt:forged"
    payload["provider_execution_binding_ref"] = binding.id
    forged = Event(
        id=dispatch_commit_identity_from_payload(payload),
        type=DISPATCH_COMMIT_EVENT,
        subject_ref="request:pt:forged",
        payload=payload,
    )
    with pytest.raises(ValueError, match="governed dispatch commit"):
        InMemoryStateStore().append_event(forged)


def test_pt_007_binding_origin_is_registry_capture_and_governed_dispatch() -> None:
    _store, registry, provider, event = _bound_dispatch("007")
    captured_provider, binding = registry.capture_execution_target(
        provider.descriptor.id,
        expected_provider=provider,
    )
    assert captured_provider is provider
    assert binding.authoritative_configuration_ref == "provider-config:target:007"
    assert event.payload["provider_execution_binding_ref"] == binding.id
    assert provider_execution_binding_from_dispatch(event) == binding


def test_pt_008_historical_backfill_from_current_state_is_closed() -> None:
    with pytest.raises(ValueError, match="historical|backfill|unsupported"):
        reject_historical_execution_binding_backfill(
            "dispatch:legacy",
            "provider:target-production",
        )


def test_pt_009_descriptor_drift_is_detected_under_same_provider_id() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    _register(registry, provider, "009")
    provider.drift()
    with pytest.raises(ValueError, match="descriptor drift"):
        registry.execution_binding(provider.descriptor.id, expected_provider=provider)


def test_pt_010_missing_current_target_is_unavailable_not_retargeted() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    historical = _register(registry, provider, "010")
    registry.unregister(provider.descriptor.id)
    assert registry.resolve_execution_binding(historical) is None


def test_pt_011_same_id_mismatched_current_binding_fails_closed() -> None:
    registry = ProviderRegistry()
    source = _Provider("source")
    historical = _register(registry, source, "011-source")
    registry.unregister(source.descriptor.id)
    current = _Provider("current")
    _register(registry, current, "011-current")
    assert registry.resolve_execution_binding(historical) is None


def test_pt_012_execution_binding_does_not_authorize_reconcile() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    binding = _register(registry, provider, "012")
    assert not hasattr(binding, "reconcile")
    assert not hasattr(binding, "consume_recovery_application")


def test_pt_013_execution_binding_does_not_authorize_invoke_or_retry() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    binding = _register(registry, provider, "013")
    assert not hasattr(binding, "invoke")
    assert not hasattr(binding, "retry")
    assert not hasattr(binding, "materialize_capability_request")


def test_pt_014_execution_binding_does_not_imply_repeatability() -> None:
    registry = ProviderRegistry()
    provider = _Provider()
    binding = _register(registry, provider, "014")
    assert not hasattr(binding, "repeat_safe")
    assert not hasattr(binding, "reconciliation_repeatability_contract")


def test_pt_015_legacy_dispatch_remains_non_upgradable() -> None:
    with pytest.raises(ValueError, match="legacy|backfill|unsupported"):
        provider_execution_binding_from_dispatch(_legacy_dispatch())


def test_pt_016_binding_bearing_dispatch_authority_import_is_closed(tmp_path: Path) -> None:
    source, _registry, _provider, event = _bound_dispatch("016")
    exported = source.export_state()
    assert any(
        raw.get("id") == event.id and "provider_execution_binding_ref" in raw.get("payload", {})
        for raw in exported["event"]
        if isinstance(raw, dict) and isinstance(raw.get("payload"), dict)
    )

    memory = InMemoryStateStore()
    memory_before = memory.export_state()
    with pytest.raises(ValueError, match="provider execution-binding|P5|import|unsupported"):
        memory.import_state({"event": [event.model_dump(mode="json")]})
    assert memory.export_state() == memory_before

    sqlite_path = tmp_path / "pt-016.db"
    sqlite = SQLiteStateStore(sqlite_path)
    sqlite_before = sqlite.export_state()
    try:
        with pytest.raises(ValueError, match="provider execution-binding|P5|import|unsupported"):
            sqlite.import_state({"event": [event.model_dump(mode="json")]})
        assert sqlite.export_state() == sqlite_before
    finally:
        sqlite.close()
    reopened = SQLiteStateStore(sqlite_path)
    try:
        assert reopened.export_state() == sqlite_before
    finally:
        reopened.close()

    legacy = _legacy_dispatch()
    legacy_memory = InMemoryStateStore()
    legacy_memory.import_state({"event": [legacy.model_dump(mode="json")]})
    assert legacy_memory.get_event(legacy.id) is not None
    legacy_sqlite = SQLiteStateStore(tmp_path / "pt-016-legacy.db")
    try:
        legacy_sqlite.import_state({"event": [legacy.model_dump(mode="json")]})
        assert legacy_sqlite.get_event(legacy.id) is not None
    finally:
        legacy_sqlite.close()

    malformed_payload = dict(event.payload)
    malformed_payload.pop("provider_execution_binding_ref", None)
    malformed = event.model_copy(
        update={
            "id": "dispatch_pt_016_embedded_only",
            "payload": malformed_payload,
        }
    )
    malformed_memory = InMemoryStateStore()
    malformed_before = malformed_memory.export_state()
    with pytest.raises(ValueError, match="provider execution-binding|P5|import|unsupported"):
        malformed_memory.import_state({"event": [malformed.model_dump(mode="json")]})
    assert malformed_memory.export_state() == malformed_before

    malformed_sqlite_path = tmp_path / "pt-016-malformed.db"
    malformed_sqlite = SQLiteStateStore(malformed_sqlite_path)
    malformed_sqlite_before = malformed_sqlite.export_state()
    try:
        with pytest.raises(ValueError, match="provider execution-binding|P5|import|unsupported"):
            malformed_sqlite.import_state({"event": [malformed.model_dump(mode="json")]})
        assert malformed_sqlite.export_state() == malformed_sqlite_before
    finally:
        malformed_sqlite.close()


def test_pt_017_reality_exit_without_durable_binding_is_unknowable() -> None:
    state = classify_historical_target_capture(
        reality_exit_may_have_occurred=True,
        durable_execution_binding_ref=None,
    )
    assert state.target_status == "unknowable"
    assert state.automated_reconciliation_allowed is False


def test_pt_separation_invocation_spec_binding_id_is_not_execution_binding_authority() -> None:
    fields = set(InvocationSpecificationCommitRequest.model_fields)
    assert "provider_binding_id" in fields
    assert "provider_execution_binding_ref" not in fields


def test_pt_separation_provider_descriptor_does_not_carry_execution_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "provider_execution_binding" not in fields
    assert "configured_execution_identity" not in fields
    assert "execution_binding_digest" not in fields
