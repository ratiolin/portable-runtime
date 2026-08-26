from __future__ import annotations

import inspect
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
from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.core.reconciliation_repeatability import (
    ReconciliationRepeatabilityAuthority,
    ReconciliationRepeatabilityConfiguration,
    ReconciliationRepeatabilityContract,
    evaluate_reconciliation_repeatability,
    reconciliation_repeatability_authority_from_dispatch,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.dispatch import (
    DISPATCH_COMMIT_EVENT,
    GovernanceDispatchCommitter,
    dispatch_commit_identity_from_payload,
)
from portable_runtime.governance.distinction import DistinctionState, UseContext
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    provider_execution_binding_from_dispatch,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


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


class _Provider:
    def __init__(self, *, effect_semantics: str = "reconcilable") -> None:
        self.calls = 0
        self.reconcile_calls = 0
        self.descriptor = ProviderDescriptor(
            id="c-provider",
            name="C provider",
            version="1",
            capabilities=["test.read"],
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
        self.calls += 1
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        del request_id
        self.reconcile_calls += 1
        raise AssertionError("C authority does not authorize provider.reconcile")


def _configuration(
    *,
    protocol_identity: str = "capability-provider.reconcile",
    protocol_version: str = "1",
    contract_version: str = "1",
    repeatability_mode: str = "repeat-safe",
) -> ReconciliationRepeatabilityConfiguration:
    return ReconciliationRepeatabilityConfiguration(
        reconciliation_protocol_identity=protocol_identity,
        reconciliation_protocol_version=protocol_version,
        repeatability_mode=repeatability_mode,
        contract_version=contract_version,
    )


def _register(
    registry: ProviderRegistry,
    provider: _Provider,
    *,
    binding_identity: str = "configured:c:stable",
    configuration_ref: str = "provider-config:c:stable",
    repeatability: ReconciliationRepeatabilityConfiguration | None = None,
) -> None:
    registry.register(
        provider,
        configured_execution_identity=binding_identity,
        authoritative_configuration_ref=configuration_ref,
        reconciliation_repeatability=repeatability,
    )


def _seed_c_dispatch(
    suffix: str,
    *,
    repeatability: ReconciliationRepeatabilityConfiguration | None = None,
) -> tuple[
    InMemoryStateStore,
    ProviderRegistry,
    _Provider,
    Event,
    ProviderExecutionBinding,
    ReconciliationRepeatabilityAuthority | None,
]:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    provider = _Provider()
    registry = ProviderRegistry()
    _register(
        registry,
        provider,
        binding_identity=f"configured:c:{suffix}",
        configuration_ref=f"provider-config:c:{suffix}",
        repeatability=repeatability,
    )

    work = Work(id=f"work:c:{suffix}", title="C integration")
    run = Run(id=f"run:c:{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step:c:{suffix}",
        run_id=run.id,
        step_key="reconcile",
        status="running",
        effect_semantics="reconcilable",
        side_effect_class="reconcilable",
        reversibility="unknown",
    )
    action = Action(
        id=f"action:c:{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="test.read",
        provider_id=provider.descriptor.id,
        request_ref=f"request:c:{suffix}",
        status="running",
    )
    attempt = StepAttempt(
        id=f"attempt:c:{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider.descriptor.id,
        request_ref=action.request_ref,
        idempotency_key=f"idem:c:{suffix}",
        status="running",
        metadata={"action_ref": action.id},
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_action(action)
    store.save_attempt(attempt)

    request = CapabilityRequest(
        id=action.request_ref,
        capability="test.read",
        work_id=work.id,
        run_id=run.id,
        idempotency_key=attempt.idempotency_key,
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
        attempt_id=attempt.id,
        provider_registry=registry,
        expected_provider=provider,
    )
    assert decision.status == "committed"
    assert decision.commit_ref is not None
    event = store.get_event(decision.commit_ref)
    assert event is not None
    binding = provider_execution_binding_from_dispatch(event)
    authority = (
        reconciliation_repeatability_authority_from_dispatch(event)
        if decision.reconciliation_repeatability_authority_ref is not None
        else None
    )
    return store, registry, provider, event, binding, authority


def test_c_int_01_exact_b_subject_and_repeat_safe_contract_are_eligible() -> None:
    _store, registry, provider, dispatch, binding, authority = _seed_c_dispatch(
        "eligible",
        repeatability=_configuration(),
    )
    assert authority is not None
    assert authority.subject_model == "request-id"
    assert authority.subject_identity == dispatch.payload["request_id"]
    assert authority.provider_execution_binding_ref == binding.id
    eligibility = registry.reconciliation_repeatability_eligibility(
        authority,
        binding,
        required_subject_identity=str(dispatch.payload["request_id"]),
    )
    assert eligibility.status == "eligible"
    assert eligibility.eligible is True
    assert provider.calls == 0
    assert provider.reconcile_calls == 0


def test_c_int_02_same_provider_id_with_different_b_is_ineligible() -> None:
    _store, _source_registry, _source_provider, dispatch, binding, authority = _seed_c_dispatch(
        "source-b",
        repeatability=_configuration(),
    )
    assert authority is not None

    current = ProviderRegistry()
    replacement = _Provider()
    _register(
        current,
        replacement,
        binding_identity="configured:c:different-b",
        configuration_ref="provider-config:c:different-b",
        repeatability=_configuration(),
    )
    eligibility = current.reconciliation_repeatability_eligibility(
        authority,
        binding,
        required_subject_identity=str(dispatch.payload["request_id"]),
    )
    assert eligibility.eligible is False
    assert replacement.reconcile_calls == 0


def test_c_int_03_same_b_with_different_request_id_is_ineligible() -> None:
    _store, registry, _provider, dispatch, binding, authority = _seed_c_dispatch(
        "subject",
        repeatability=_configuration(),
    )
    assert authority is not None
    eligibility = registry.reconciliation_repeatability_eligibility(
        authority,
        binding,
        required_subject_identity="request:c:other",
    )
    assert eligibility.eligible is False

    tampered_payload = dict(dispatch.payload)
    tampered_payload["request_id"] = "request:c:other"
    tampered = Event(
        id=dispatch_commit_identity_from_payload(tampered_payload),
        type=DISPATCH_COMMIT_EVENT,
        subject_ref="request:c:other",
        payload=tampered_payload,
    )
    with pytest.raises(ValueError, match="subject"):
        reconciliation_repeatability_authority_from_dispatch(tampered)


def test_c_int_04_protocol_version_drift_is_ineligible() -> None:
    _store, registry, provider, dispatch, binding, authority = _seed_c_dispatch(
        "protocol-drift",
        repeatability=_configuration(protocol_version="1"),
    )
    assert authority is not None
    registry.unregister(provider.descriptor.id)
    replacement = _Provider()
    _register(
        registry,
        replacement,
        binding_identity="configured:c:protocol-drift",
        configuration_ref="provider-config:c:protocol-drift",
        repeatability=_configuration(protocol_version="2"),
    )
    assert registry.execution_binding(replacement.descriptor.id) == binding
    eligibility = registry.reconciliation_repeatability_eligibility(
        authority,
        binding,
        required_subject_identity=str(dispatch.payload["request_id"]),
    )
    assert eligibility.eligible is False
    assert "drift" in eligibility.reason.lower()


def test_c_int_05_contract_version_and_digest_drift_are_ineligible() -> None:
    _store, registry, provider, dispatch, binding, authority = _seed_c_dispatch(
        "contract-drift",
        repeatability=_configuration(contract_version="1"),
    )
    assert authority is not None
    historical_digest = authority.contract_digest
    registry.unregister(provider.descriptor.id)
    replacement = _Provider()
    _register(
        registry,
        replacement,
        binding_identity="configured:c:contract-drift",
        configuration_ref="provider-config:c:contract-drift",
        repeatability=_configuration(contract_version="2"),
    )
    current_contract = registry.reconciliation_repeatability_contract(
        replacement.descriptor.id,
        expected_provider=replacement,
    )
    assert current_contract is not None
    assert current_contract.contract_digest != historical_digest
    eligibility = registry.reconciliation_repeatability_eligibility(
        authority,
        binding,
        required_subject_identity=str(dispatch.payload["request_id"]),
    )
    assert eligibility.eligible is False


@pytest.mark.parametrize("effect_semantics", ["idempotent", "reconcilable"])
def test_c_int_06_business_effect_semantics_alone_create_no_repeatability_authority(
    effect_semantics: str,
) -> None:
    registry = ProviderRegistry()
    provider = _Provider(effect_semantics=effect_semantics)
    _register(
        registry,
        provider,
        binding_identity=f"configured:c:{effect_semantics}",
        configuration_ref=f"provider-config:c:{effect_semantics}",
        repeatability=None,
    )
    captured, _binding, authority = registry.capture_reconciliation_execution_target(
        provider.descriptor.id,
        subject_identity=f"request:c:{effect_semantics}",
        expected_provider=provider,
    )
    assert captured is provider
    assert authority is None
    assert registry.reconciliation_repeatability_contract(provider.descriptor.id) is None


def test_c_int_07_ad_hoc_repeat_safe_and_serialized_authority_do_not_establish_c(
    tmp_path: Path,
) -> None:
    signature = inspect.signature(ProviderRegistry.register)
    assert "repeat_safe" not in signature.parameters
    assert "contract_digest" not in ReconciliationRepeatabilityConfiguration.model_fields

    store, _registry, _provider, dispatch, _binding, authority = _seed_c_dispatch(
        "origin",
        repeatability=_configuration(),
    )
    assert authority is not None

    memory = InMemoryStateStore()
    with pytest.raises(ValueError, match="governed dispatch commit"):
        memory.append_event(dispatch)
    with pytest.raises(ValueError, match="P5|execution-binding|import"):
        memory.import_state({"event": [dispatch.model_dump(mode="json")]})
    assert memory.list_events() == []

    sqlite = SQLiteStateStore(tmp_path / "c-origin.db")
    try:
        with pytest.raises(ValueError, match="governed dispatch commit"):
            sqlite.append_event(dispatch)
        with pytest.raises(ValueError, match="P5|execution-binding|import"):
            sqlite.import_state({"event": [dispatch.model_dump(mode="json")]})
        assert sqlite.list_events() == []
    finally:
        sqlite.close()

    # The source store remains authoritative and unchanged by failed copies.
    assert store.get_event(dispatch.id) == dispatch


def test_c_int_08_c_objects_have_no_invoke_reconcile_or_retry_capability() -> None:
    _store, registry, provider, dispatch, binding, authority = _seed_c_dispatch(
        "non-executing",
        repeatability=_configuration(),
    )
    assert authority is not None
    contract = registry.reconciliation_repeatability_contract(
        provider.descriptor.id,
        expected_provider=provider,
    )
    assert contract is not None
    for obj in (
        ReconciliationRepeatabilityConfiguration,
        ReconciliationRepeatabilityContract,
        ReconciliationRepeatabilityAuthority,
        type(
            evaluate_reconciliation_repeatability(
                authority,
                historical_binding=binding,
                current_contract=contract,
                required_subject_identity=str(dispatch.payload["request_id"]),
            )
        ),
    ):
        assert not hasattr(obj, "invoke")
        assert not hasattr(obj, "reconcile")
        assert not hasattr(obj, "retry")
        assert not hasattr(obj, "materialize_capability_request")
    assert provider.calls == 0
    assert provider.reconcile_calls == 0


def test_c_unknown_or_non_repeat_safe_configuration_produces_no_positive_authority() -> None:
    for mode in ("unknown", "non-repeat-safe"):
        registry = ProviderRegistry()
        provider = _Provider()
        _register(
            registry,
            provider,
            binding_identity=f"configured:c:{mode}",
            configuration_ref=f"provider-config:c:{mode}",
            repeatability=_configuration(repeatability_mode=mode),
        )
        _provider, binding, authority = registry.capture_reconciliation_execution_target(
            provider.descriptor.id,
            subject_identity=f"request:c:{mode}",
            expected_provider=provider,
        )
        assert authority is None
        contract = registry.reconciliation_repeatability_contract(provider.descriptor.id)
        assert contract is not None
        assert contract.provider_execution_binding_ref == binding.id
        assert contract.repeatability_mode == mode


def test_c_legacy_or_b_only_dispatch_has_no_repeatability_backfill() -> None:
    _store, _registry, _provider, dispatch, _binding, authority = _seed_c_dispatch(
        "b-only",
        repeatability=None,
    )
    assert authority is None
    assert "provider_execution_binding_ref" in dispatch.payload
    assert "reconciliation_repeatability_authority_ref" not in dispatch.payload
    with pytest.raises(ValueError, match="historical|backfill|unsupported"):
        reconciliation_repeatability_authority_from_dispatch(dispatch)


def test_c_provider_protocol_shape_is_unchanged() -> None:
    assert list(inspect.signature(CapabilityProvider.reconcile).parameters) == [
        "self",
        "request_id",
    ]
