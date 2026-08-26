from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import portable_runtime.core.boundary as boundary_module
from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
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
    provider_execution_binding_from_dispatch,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.recovery_disposition import RecoveryDispositionCommitRequest
from portable_runtime.workflows.recovery_observation import RecoveryObservationCommitRequest


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
    def __init__(self, marker: str = "v1") -> None:
        self.calls = 0
        self.marker = marker
        self._descriptor = ProviderDescriptor(
            id="b-provider",
            name="B provider",
            version=marker,
            capabilities=["test.read"],
            side_effect_class="pure",
            effect_semantics="pure",
            reversibility="reversible",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def drift_descriptor(self) -> None:
        self._descriptor = self._descriptor.model_copy(update={"version": f"{self.marker}-drift"})

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
        raise AssertionError("B does not authorize reconciliation")


def _register(registry: ProviderRegistry, provider: _Provider, suffix: str) -> None:
    registry.register(
        provider,
        configured_execution_identity=f"configured:b:{suffix}",
        authoritative_configuration_ref=f"provider-config:b:{suffix}",
    )


def _boundary(store: InMemoryStateStore, registry: ProviderRegistry) -> RealityBoundary:
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    return RealityBoundary(
        store=store,
        registry=registry,
        governance_requirement_resolver=_requirement,
    )


def _boundary_request(suffix: str) -> CapabilityRequest:
    return CapabilityRequest(
        id=f"request:b:{suffix}",
        capability="test.read",
        idempotency_key=f"idem:b:{suffix}",
    )


def _seed_bound_dispatch(
    suffix: str,
) -> tuple[InMemoryStateStore, ProviderRegistry, _Provider, Event]:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    provider = _Provider()
    registry = ProviderRegistry()
    _register(registry, provider, suffix)

    work = Work(id=f"work:b:{suffix}", title="B integration")
    run = Run(id=f"run:b:{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step:b:{suffix}",
        run_id=run.id,
        step_key="reconcile",
        status="running",
        effect_semantics="reconcilable",
        side_effect_class="reconcilable",
        reversibility="unknown",
    )
    action = Action(
        id=f"action:b:{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="test.read",
        provider_id=provider.descriptor.id,
        request_ref=f"request:b:{suffix}",
        status="running",
    )
    attempt = StepAttempt(
        id=f"attempt:b:{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider.descriptor.id,
        request_ref=action.request_ref,
        idempotency_key=f"idem:b:{suffix}",
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
    assert decision.provider_execution_binding_ref is not None
    event = store.get_event(decision.commit_ref)
    assert event is not None
    return store, registry, provider, event


async def test_b_int_01_same_id_replacement_between_lookup_and_dispatch_fails_closed(
    monkeypatch: Any,
) -> None:
    store = InMemoryStateStore()
    registry = ProviderRegistry()
    original = _Provider("old")
    replacement = _Provider("new")
    _register(registry, original, "old")
    real_committer = GovernanceDispatchCommitter

    class ReplacingCommitter:
        def __init__(self, target_store: Any) -> None:
            self.store = target_store

        def commit(self, *args: Any, **kwargs: Any) -> Any:
            registry.unregister(original.descriptor.id)
            _register(registry, replacement, "new")
            return real_committer(self.store).commit(*args, **kwargs)

    monkeypatch.setattr(boundary_module, "GovernanceDispatchCommitter", ReplacingCommitter)
    result = await _boundary(store, registry).execute(_boundary_request("race"))

    assert original.calls == 0
    assert replacement.calls == 0
    assert result.status == "unavailable"
    assert result.error is not None
    assert not [event for event in store.list_events() if event.type == DISPATCH_COMMIT_EVENT]


def test_b_int_02_bound_dispatch_recovery_observation_reconstruction_succeeds() -> None:
    store, _registry, _provider, dispatch = _seed_bound_dispatch("obs")
    observation = store.commit_recovery_observation(
        RecoveryObservationCommitRequest(
            observation_instance_ref="observation-instance:b:obs",
            dispatch_commit_ref=dispatch.id,
            observation_source="manual-check",
            reported_status="reported-unknown",
        )
    )
    assert observation.dispatch_commit_ref == dispatch.id
    assert provider_execution_binding_from_dispatch(dispatch).id == dispatch.payload[
        "provider_execution_binding_ref"
    ]


def test_b_int_03_bound_dispatch_recovery_disposition_reconstruction_succeeds() -> None:
    store, _registry, _provider, dispatch = _seed_bound_dispatch("disposition")
    observation = store.commit_recovery_observation(
        RecoveryObservationCommitRequest(
            observation_instance_ref="observation-instance:b:disposition",
            dispatch_commit_ref=dispatch.id,
            observation_source="manual-check",
            reported_status="reported-unknown",
        )
    )
    disposition = store.commit_recovery_disposition(
        RecoveryDispositionCommitRequest(
            dispatch_commit_ref=dispatch.id,
            observation_refs=(observation.id,),
            outcome_refs=(),
            policy_ref="policy:b:reconcile",
        ),
        lambda _basis: "reconcile-again",
    )
    assert disposition.dispatch_commit_ref == dispatch.id
    assert disposition.action == "reconcile-again"


def test_b_int_04_legacy_dispatch_identity_is_unchanged_and_unbound() -> None:
    payload = {
        "schema": DISPATCH_COMMIT_SCHEMA,
        "request_id": "request:b:legacy",
        "provider_id": "b-provider",
        "attempt_ref": "attempt:b:legacy",
        "invocation_permit_digest": "permit:b:legacy",
        "qualification_digest": "",
        "governance_requirement_digest": "requirement:b:legacy",
        "governance_snapshot_digest": "snapshot:b:legacy",
        "lease_generation": 0,
        "linearization_domain": "authoritative-state-store",
    }
    legacy_identity_payload = {
        "schema": DISPATCH_COMMIT_SCHEMA,
        "request_id": payload["request_id"],
        "provider_id": payload["provider_id"],
        "attempt_id": payload["attempt_ref"],
        "invocation_permit_digest": payload["invocation_permit_digest"],
        "governance_requirement_digest": payload["governance_requirement_digest"],
        "governance_snapshot_digest": payload["governance_snapshot_digest"],
    }
    raw = json.dumps(legacy_identity_payload, sort_keys=True, separators=(",", ":"))
    expected = f"dispatch_{hashlib.sha256(raw.encode()).hexdigest()}"
    assert dispatch_commit_identity_from_payload(payload) == expected

    event = Event(
        id=expected,
        type=DISPATCH_COMMIT_EVENT,
        subject_ref=str(payload["request_id"]),
        payload=payload,
    )
    store = InMemoryStateStore()
    store.append_event(event)
    assert store.get_event(expected) is not None
    try:
        provider_execution_binding_from_dispatch(event)
    except ValueError as exc:
        assert "legacy" in str(exc).lower() or "backfill" in str(exc).lower()
    else:
        raise AssertionError("legacy dispatch must not acquire execution-binding authority")


def test_b_int_05_direct_binding_bearing_dispatch_cannot_establish_authority(
    tmp_path: Path,
) -> None:
    _store, registry, provider, dispatch = _seed_bound_dispatch("forged-source")
    binding = registry.execution_binding(provider.descriptor.id, expected_provider=provider)
    forged_payload = dict(dispatch.payload)
    forged_payload["request_id"] = "request:b:forged"
    forged = Event(
        id=dispatch_commit_identity_from_payload(forged_payload),
        type=DISPATCH_COMMIT_EVENT,
        subject_ref="request:b:forged",
        payload=forged_payload,
    )

    memory = InMemoryStateStore()
    try:
        memory.append_event(forged)
    except ValueError as exc:
        assert "governed dispatch commit" in str(exc)
    else:
        raise AssertionError("direct B-aware dispatch append must fail closed")

    sqlite = SQLiteStateStore(tmp_path / "b-int-05.db")
    try:
        try:
            sqlite.append_event(forged)
        except ValueError as exc:
            assert "governed dispatch commit" in str(exc)
        else:
            raise AssertionError("direct SQLite B-aware dispatch append must fail closed")
    finally:
        sqlite.close()

    assert binding.id == forged.payload["provider_execution_binding_ref"]


async def test_b_int_06_descriptor_drift_before_dispatch_blocks_reality_exit(
    monkeypatch: Any,
) -> None:
    store = InMemoryStateStore()
    registry = ProviderRegistry()
    provider = _Provider("stable")
    _register(registry, provider, "stable")
    real_committer = GovernanceDispatchCommitter

    class DriftingCommitter:
        def __init__(self, target_store: Any) -> None:
            self.store = target_store

        def commit(self, *args: Any, **kwargs: Any) -> Any:
            provider.drift_descriptor()
            return real_committer(self.store).commit(*args, **kwargs)

    monkeypatch.setattr(boundary_module, "GovernanceDispatchCommitter", DriftingCommitter)
    result = await _boundary(store, registry).execute(_boundary_request("drift"))

    assert provider.calls == 0
    assert result.status == "unavailable"
    assert result.error is not None
    assert not [event for event in store.list_events() if event.type == DISPATCH_COMMIT_EVENT]
