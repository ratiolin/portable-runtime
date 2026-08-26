"""B4 reconciliation consumer production graduation.

RCX-001..025 are real production tests.  No test-side consumer simulation is
used: each positive path creates a governed B/C-aware dispatch, durable recovery
observation, RecoveryDisposition, and RecoveryApplication, then drives the
production RecoveryReconciliationConsumer.
"""

from __future__ import annotations

import asyncio
import inspect
from collections import Counter
from dataclasses import dataclass
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
from portable_runtime.core.reconciliation_boundary import (
    RecoveryReconciliationRealityBoundary,
)
from portable_runtime.core.reconciliation_repeatability import (
    ReconciliationRepeatabilityConfiguration,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.governance.distinction import DistinctionState, UseContext
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.stores.recovery_application_observation import (
    RecoveryApplicationObservationInMemoryStateStore,
)
from portable_runtime.workflows.recovery_application import (
    RecoveryApplicationCommitRequest,
)
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
)
from portable_runtime.workflows.recovery_disposition import (
    RecoveryDispositionCommitRequest,
)
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservationCommitRequest,
)
from portable_runtime.workflows.recovery_reconciliation import (
    RecoveryReconciliationConsumer,
    RecoveryReconciliationRequest,
)


class _Policy:
    def __init__(self, action: str) -> None:
        self.action = action

    def decide(self, _basis: Any) -> str:
        return self.action


class _Provider:
    def __init__(self, provider_id: str = "provider:consumer") -> None:
        self.invoke_calls = 0
        self.reconcile_calls = 0
        self.reconcile_request_ids: list[str] = []
        self.reconcile_statuses: list[str] = ["succeeded"]
        self.block_until_two = False
        self.two_entered = asyncio.Event()
        self.release = asyncio.Event()
        self.descriptor = ProviderDescriptor(
            id=provider_id,
            name="reconciliation consumer provider",
            version="1",
            capabilities=["test.read"],
            effect_semantics="reconcilable",
            side_effect_class="reconcilable",
            reversibility="unknown",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        del context
        self.invoke_calls += 1
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult:
        index = self.reconcile_calls
        self.reconcile_calls += 1
        self.reconcile_request_ids.append(request_id)
        if self.block_until_two:
            if self.reconcile_calls >= 2:
                self.two_entered.set()
            await self.release.wait()
        status = self.reconcile_statuses[min(index, len(self.reconcile_statuses) - 1)]
        return CapabilityResult(
            request_id=request_id,
            provider_id=self.descriptor.id,
            status=status,
        )


class _CountingRegistry(ProviderRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.binding_resolutions = 0
        self.repeatability_evaluations = 0

    def resolve_execution_binding(self, historical):  # type: ignore[no-untyped-def]
        self.binding_resolutions += 1
        return super().resolve_execution_binding(historical)

    def reconciliation_repeatability_eligibility(  # type: ignore[no-untyped-def]
        self,
        historical_authority,
        historical_binding,
        *,
        required_subject_identity,
    ):
        self.repeatability_evaluations += 1
        return super().reconciliation_repeatability_eligibility(
            historical_authority,
            historical_binding,
            required_subject_identity=required_subject_identity,
        )

    def reset_counts(self) -> None:
        self.binding_resolutions = 0
        self.repeatability_evaluations = 0


class _StoreProxy:
    def __init__(
        self,
        base: RecoveryApplicationObservationInMemoryStateStore,
        *,
        application_override: Event | None = None,
        dispatch_override: Event | None = None,
        fail_a_commit: bool = False,
    ) -> None:
        self.base = base
        self.application_override = application_override
        self.dispatch_override = dispatch_override
        self.fail_a_commit = fail_a_commit

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def get_event(self, event_id: str):  # type: ignore[no-untyped-def]
        if self.application_override is not None and event_id == self.application_override.id:
            return self.application_override
        if self.dispatch_override is not None and event_id == self.dispatch_override.id:
            return self.dispatch_override
        return self.base.get_event(event_id)

    def commit_recovery_application_observation(
        self,
        request: RecoveryApplicationObservationCommitRequest,
    ):
        if self.fail_a_commit:
            raise RuntimeError("injected A commit failure")
        return self.base.commit_recovery_application_observation(request)


@dataclass
class _Seed:
    store: RecoveryApplicationObservationInMemoryStateStore
    registry: _CountingRegistry
    provider: _Provider
    application: Any
    dispatch: Event
    step: Step
    generic_observation: Any
    binding_identity: str
    configuration_ref: str

    def consumer(
        self,
        *,
        store: Any | None = None,
        registry: ProviderRegistry | None = None,
    ) -> RecoveryReconciliationConsumer:
        return RecoveryReconciliationConsumer(
            store=store or self.store,
            registry=registry or self.registry,
        )


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
        scheme_id="consumer-governance",
        use_context=UseContext("consumer-context", frozenset({"a"})),
    )


def _repeatability(
    *,
    protocol_version: str = "1",
    contract_version: str = "1",
) -> ReconciliationRepeatabilityConfiguration:
    return ReconciliationRepeatabilityConfiguration(
        reconciliation_protocol_identity="capability-provider.reconcile",
        reconciliation_protocol_version=protocol_version,
        repeatability_mode="repeat-safe",
        contract_version=contract_version,
    )


def _seed(
    suffix: str,
    *,
    repeatability: ReconciliationRepeatabilityConfiguration | None = None,
    include_registry_authority: bool = True,
    disposition_action: str = "reconcile-again",
) -> _Seed:
    store = RecoveryApplicationObservationInMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state(
        "consumer-governance",
        _state(),
    )
    registry = _CountingRegistry()
    provider = _Provider()
    binding_identity = f"configured:consumer:{suffix}"
    configuration_ref = f"provider-config:consumer:{suffix}"
    registry.register(
        provider,
        configured_execution_identity=binding_identity,
        authoritative_configuration_ref=configuration_ref,
        reconciliation_repeatability=repeatability,
    )

    work = Work(id=f"work:consumer:{suffix}", title="consumer integration")
    run = Run(id=f"run:consumer:{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step:consumer:{suffix}",
        run_id=run.id,
        step_key="reconcile",
        status="unknown",
        current_attempt=1,
        effect_semantics="reconcilable",
        side_effect_class="reconcilable",
        reversibility="unknown",
    )
    action = Action(
        id=f"action:consumer:{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="test.read",
        provider_id=provider.descriptor.id,
        request_ref=f"request:consumer:{suffix}",
        status="unknown",
    )
    attempt = StepAttempt(
        id=f"attempt:consumer:{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider.descriptor.id,
        request_ref=action.request_ref,
        idempotency_key=f"idem:consumer:{suffix}",
        status="unknown",
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
    kwargs: dict[str, Any] = {}
    if include_registry_authority:
        kwargs = {"provider_registry": registry, "expected_provider": provider}
    decision = GovernanceDispatchCommitter(store).commit(
        request,
        permit,
        _requirement,
        attempt_id=attempt.id,
        **kwargs,
    )
    assert decision.status == "committed"
    assert decision.commit_ref is not None
    dispatch = store.get_event(decision.commit_ref)
    assert dispatch is not None

    generic = store.commit_recovery_observation(
        RecoveryObservationCommitRequest(
            observation_instance_ref=f"observation:consumer:{suffix}",
            dispatch_commit_ref=dispatch.id,
            observation_source="provider-reconcile",
            reported_status="reported-unknown",
            provenance_refs=(provider.descriptor.id,),
        )
    )
    disposition = store.commit_recovery_disposition(
        RecoveryDispositionCommitRequest(
            dispatch_commit_ref=dispatch.id,
            observation_refs=(generic.id,),
            outcome_refs=(),
            policy_ref=f"policy:consumer:{suffix}",
        ),
        policy=_Policy(disposition_action),
    )
    application = store.commit_recovery_application(
        RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    )
    registry.reset_counts()
    return _Seed(
        store=store,
        registry=registry,
        provider=provider,
        application=application,
        dispatch=dispatch,
        step=step,
        generic_observation=generic,
        binding_identity=binding_identity,
        configuration_ref=configuration_ref,
    )


def _replace_provider(
    seed: _Seed,
    *,
    binding_identity: str | None = None,
    configuration_ref: str | None = None,
    repeatability: ReconciliationRepeatabilityConfiguration | None = None,
) -> _Provider:
    seed.registry.unregister(seed.provider.descriptor.id)
    replacement = _Provider(seed.provider.descriptor.id)
    seed.registry.register(
        replacement,
        configured_execution_identity=binding_identity or seed.binding_identity,
        authoritative_configuration_ref=configuration_ref or seed.configuration_ref,
        reconciliation_repeatability=repeatability,
    )
    seed.registry.reset_counts()
    return replacement


def _event_counts(store: Any) -> Counter[str]:
    return Counter(event.type for event in store.list_events())


# RCX-001

def test_rcx_001_request_surface_is_exact_recovery_application_only() -> None:
    assert set(RecoveryReconciliationRequest.__dataclass_fields__) == {
        "recovery_application_ref"
    }


# RCX-002

async def test_rcx_002_missing_application_zero_calls() -> None:
    seed = _seed("missing-app", repeatability=_repeatability())
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest("recovery_application:missing")
    )
    assert result.status == "unavailable"
    assert seed.provider.reconcile_calls == 0


# RCX-003

async def test_rcx_003_wrong_application_kind_zero_calls() -> None:
    seed = _seed(
        "wrong-kind",
        repeatability=_repeatability(),
        disposition_action="hold-unresolved",
    )
    assert seed.application.application_kind == "hold"
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert seed.provider.reconcile_calls == 0


# RCX-004

async def test_rcx_004_application_graph_rebound_zero_calls() -> None:
    seed = _seed("graph-rebound", repeatability=_repeatability())
    event = seed.store.get_event(seed.application.id)
    assert event is not None
    payload = dict(event.payload)
    payload["source_step_ref"] = "step:rebound"
    proxy = _StoreProxy(
        seed.store,
        application_override=event.model_copy(update={"payload": payload}),
    )
    result = await seed.consumer(store=proxy).consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "conflicted"
    assert seed.provider.reconcile_calls == 0


# RCX-005

async def test_rcx_005_a_first_replays_before_registry_resolution() -> None:
    seed = _seed("a-first", repeatability=_repeatability())
    completed = seed.store.commit_recovery_application_observation(
        RecoveryApplicationObservationCommitRequest(
            recovery_application_ref=seed.application.id,
            observation_source="preexisting-completion",
            reported_status="reported-unknown",
            provenance_refs=("authority:a-first",),
        )
    )
    seed.registry.unregister(seed.provider.descriptor.id)
    seed.registry.reset_counts()
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "replayed"
    assert result.recovery_observation_ref == completed.id
    assert seed.provider.reconcile_calls == 0
    assert seed.registry.binding_resolutions == 0
    assert seed.registry.repeatability_evaluations == 0


# RCX-006

async def test_rcx_006_generic_observation_does_not_satisfy_a() -> None:
    seed = _seed("generic-not-a", repeatability=_repeatability())
    assert seed.generic_observation.recovery_application_ref is None
    assert seed.store.get_recovery_application_observation(seed.application.id) is None
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "completed"
    assert seed.provider.reconcile_calls == 1


# RCX-007

async def test_rcx_007_historical_dispatch_without_b_zero_calls() -> None:
    seed = _seed(
        "missing-b",
        repeatability=_repeatability(),
        include_registry_authority=False,
    )
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert "binding" in result.reason.lower()
    assert seed.provider.reconcile_calls == 0


# RCX-008

async def test_rcx_008_same_provider_id_different_b_zero_calls() -> None:
    seed = _seed("different-b", repeatability=_repeatability())
    replacement = _replace_provider(
        seed,
        binding_identity="configured:consumer:replacement",
        configuration_ref="provider-config:consumer:replacement",
        repeatability=_repeatability(),
    )
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert replacement.reconcile_calls == 0


# RCX-009

async def test_rcx_009_historical_target_unavailable_zero_calls() -> None:
    seed = _seed("target-unavailable", repeatability=_repeatability())
    seed.registry.unregister(seed.provider.descriptor.id)
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert seed.provider.reconcile_calls == 0


# RCX-010

async def test_rcx_010_historical_c_absent_zero_calls() -> None:
    seed = _seed("missing-c", repeatability=None)
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert "repeatability" in result.reason.lower()
    assert seed.provider.reconcile_calls == 0


# RCX-011

async def test_rcx_011_corrupt_historical_c_subject_zero_calls() -> None:
    seed = _seed("c-subject", repeatability=_repeatability())
    payload = dict(seed.dispatch.payload)
    authority = dict(payload["reconciliation_repeatability_authority"])
    authority["subject_identity"] = "request:other"
    payload["reconciliation_repeatability_authority"] = authority
    proxy = _StoreProxy(
        seed.store,
        dispatch_override=seed.dispatch.model_copy(update={"payload": payload}),
    )
    result = await seed.consumer(store=proxy).consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status in {"conflicted", "unavailable"}
    assert seed.provider.reconcile_calls == 0


# RCX-012

@pytest.mark.parametrize(
    "replacement_repeatability",
    [
        _repeatability(protocol_version="2"),
        _repeatability(contract_version="2"),
    ],
)
async def test_rcx_012_c_protocol_or_contract_drift_zero_calls(
    replacement_repeatability: ReconciliationRepeatabilityConfiguration,
) -> None:
    seed = _seed("c-drift", repeatability=_repeatability())
    replacement = _replace_provider(
        seed,
        repeatability=replacement_repeatability,
    )
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert "drift" in result.reason.lower()
    assert replacement.reconcile_calls == 0


# RCX-013

async def test_rcx_013_current_only_repeat_safe_c_cannot_backfill_history() -> None:
    seed = _seed("current-only-c", repeatability=None)
    replacement = _replace_provider(seed, repeatability=_repeatability())
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "unavailable"
    assert replacement.reconcile_calls == 0


# RCX-014

async def test_rcx_014_exact_abc_crosses_reconcile_only_never_invoke() -> None:
    seed = _seed("exact-abc", repeatability=_repeatability())
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "completed"
    assert seed.provider.reconcile_calls == 1
    assert seed.provider.invoke_calls == 0


# RCX-015

async def test_rcx_015_exact_historical_request_and_resolved_target_reach_reality_exit() -> None:
    seed = _seed("exact-target", repeatability=_repeatability())
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "completed"
    assert seed.provider.reconcile_request_ids == [seed.application.source_request_ref]
    boundary_source = inspect.getsource(
        RecoveryReconciliationRealityBoundary.reconcile_exact_target
    )
    assert "registry" not in boundary_source
    assert "CapabilityRequest" not in boundary_source


# RCX-016

async def test_rcx_016_provider_result_commits_application_bound_a_directly() -> None:
    seed = _seed("a-commit", repeatability=_repeatability())
    before_unbound = sum(
        1
        for event in seed.store.list_events()
        if event.type == "RecoveryObservationRecorded"
        and event.payload.get("recovery_application_ref") is None
    )
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    observation = seed.store.get_recovery_application_observation(seed.application.id)
    assert result.status == "completed"
    assert observation is not None
    assert observation.recovery_application_ref == seed.application.id
    after_unbound = sum(
        1
        for event in seed.store.list_events()
        if event.type == "RecoveryObservationRecorded"
        and event.payload.get("recovery_application_ref") is None
    )
    assert after_unbound == before_unbound


# RCX-017

async def test_rcx_017_provider_return_plus_failed_a_commit_is_not_completion() -> None:
    seed = _seed("a-failure", repeatability=_repeatability())
    proxy = _StoreProxy(seed.store, fail_a_commit=True)
    before = _event_counts(seed.store)
    result = await seed.consumer(store=proxy).consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    after = _event_counts(seed.store)
    assert result.status == "unknown"
    assert result.durable_completion is False
    assert seed.provider.reconcile_calls == 1
    assert seed.store.get_recovery_application_observation(seed.application.id) is None
    assert after["OutcomeConfirmed"] == before["OutcomeConfirmed"]
    assert after["RecoveryDispositionRecorded"] == before["RecoveryDispositionRecorded"]
    assert after["RecoveryApplicationRecorded"] == before["RecoveryApplicationRecorded"]


# RCX-018

async def test_rcx_018_repeat_safe_allows_overlap_before_a_is_durable() -> None:
    seed = _seed("overlap", repeatability=_repeatability())
    seed.provider.block_until_two = True
    consumer = seed.consumer()
    request = RecoveryReconciliationRequest(seed.application.id)
    first = asyncio.create_task(consumer.consume(request))
    second = asyncio.create_task(consumer.consume(request))
    await asyncio.wait_for(seed.provider.two_entered.wait(), timeout=2)
    seed.provider.release.set()
    results = await asyncio.gather(first, second)
    assert seed.provider.reconcile_calls == 2
    assert all(result.status == "completed" for result in results)
    observation = seed.store.get_recovery_application_observation(seed.application.id)
    assert observation is not None


# RCX-019

async def test_rcx_019_after_a_all_same_application_calls_are_zero_call_replays() -> None:
    seed = _seed("post-a", repeatability=_repeatability())
    first = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert first.status == "completed"
    assert seed.provider.reconcile_calls == 1
    seed.registry.unregister(seed.provider.descriptor.id)
    seed.registry.reset_counts()
    second = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert second.status == "replayed"
    assert seed.provider.reconcile_calls == 1
    assert seed.registry.binding_resolutions == 0
    assert seed.registry.repeatability_evaluations == 0


# RCX-020

async def test_rcx_020_consumer_creates_no_fresh_invocation_chain() -> None:
    seed = _seed("no-fresh-chain", repeatability=_repeatability())
    attempts_before = [attempt.id for attempt in seed.store.list_attempts(seed.step.id)]
    dispatches_before = _event_counts(seed.store)["InvocationDispatchCommitted"]
    source = inspect.getsource(RecoveryReconciliationConsumer.consume)
    for forbidden in (
        "CapabilityRequest(",
        "InvocationPermit",
        "StepAttempt(",
        "GovernanceDispatchCommitter",
        ".invoke(",
    ):
        assert forbidden not in source
    await seed.consumer().consume(RecoveryReconciliationRequest(seed.application.id))
    assert [attempt.id for attempt in seed.store.list_attempts(seed.step.id)] == attempts_before
    assert _event_counts(seed.store)["InvocationDispatchCommitted"] == dispatches_before
    assert seed.provider.invoke_calls == 0


# RCX-021

async def test_rcx_021_consumer_creates_no_outcome_disposition_or_new_application() -> None:
    seed = _seed("no-decision-chain", repeatability=_repeatability())
    before = _event_counts(seed.store)
    await seed.consumer().consume(RecoveryReconciliationRequest(seed.application.id))
    after = _event_counts(seed.store)
    assert after["RecoveryDispositionRecorded"] == before["RecoveryDispositionRecorded"]
    assert after["RecoveryApplicationRecorded"] == before["RecoveryApplicationRecorded"]
    assert after["OutcomeConfirmed"] == before["OutcomeConfirmed"]


# RCX-022

async def test_rcx_022_no_reconciliation_attempt_fact() -> None:
    seed = _seed("no-reconciliation-attempt", repeatability=_repeatability())
    await seed.consumer().consume(RecoveryReconciliationRequest(seed.application.id))
    assert _event_counts(seed.store)["RecoveryReconciliationAttemptRecorded"] == 0


# RCX-023

async def test_rcx_023_no_generic_recovery_application_consumed_fact() -> None:
    seed = _seed("no-consumed", repeatability=_repeatability())
    await seed.consumer().consume(RecoveryReconciliationRequest(seed.application.id))
    assert _event_counts(seed.store)["RecoveryApplicationConsumed"] == 0


# RCX-024

async def test_rcx_024_legacy_runtime_reconcile_is_zero_provider_call_compatibility_only() -> None:
    seed = _seed("legacy-runtime", repeatability=_repeatability())
    source = inspect.getsource(Runtime.reconcile)
    assert "self.capabilities.reconcile" not in source
    assert "RecoveryApplication" in source
    runtime = Runtime(store=seed.store, registry=seed.registry)
    result = await runtime.reconcile(seed.step.id)
    assert result is not None
    assert result.status == "unknown"
    assert result.error is not None
    assert result.error["code"] == "RecoveryApplicationRequired"
    assert seed.provider.reconcile_calls == 0


# RCX-025

async def test_rcx_025_p5_cannot_manufacture_consumer_completion_authority() -> None:
    seed = _seed("p5-closed", repeatability=_repeatability())
    result = await seed.consumer().consume(
        RecoveryReconciliationRequest(seed.application.id)
    )
    assert result.status == "completed"
    exported = seed.store.export_state()
    target = RecoveryApplicationObservationInMemoryStateStore()
    with pytest.raises(ValueError, match="P5|application-bound RecoveryObservation"):
        target.import_state(exported)
    assert not hasattr(RecoveryReconciliationConsumer, "consume_serialized_authority")


async def test_overlapping_incompatible_results_linearize_one_a_and_fail_closed() -> None:
    seed = _seed("overlap-conflict", repeatability=_repeatability())
    seed.provider.reconcile_statuses = ["succeeded", "failed"]
    seed.provider.block_until_two = True
    consumer = seed.consumer()
    request = RecoveryReconciliationRequest(seed.application.id)
    first = asyncio.create_task(consumer.consume(request))
    second = asyncio.create_task(consumer.consume(request))
    await asyncio.wait_for(seed.provider.two_entered.wait(), timeout=2)
    seed.provider.release.set()
    results = await asyncio.gather(first, second)
    statuses = Counter(result.status for result in results)
    assert statuses["completed"] == 1
    assert statuses["conflicted"] == 1
    bound = [
        event
        for event in seed.store.list_events()
        if event.type == "RecoveryObservationRecorded"
        and event.payload.get("recovery_application_ref") == seed.application.id
    ]
    assert len(bound) == 1


def test_authoritative_consumer_call_graph_never_uses_legacy_boundary_reconcile() -> None:
    consumer_source = inspect.getsource(RecoveryReconciliationConsumer.consume)
    assert "reconcile_exact_target" in consumer_source
    assert "self.reality_boundary.reconcile(" not in consumer_source
