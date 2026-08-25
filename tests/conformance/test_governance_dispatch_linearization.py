from __future__ import annotations

import threading
from dataclasses import replace
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
from portable_runtime.core.models import Event, Run, Step, StepAttempt, Work
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.governance.canonical import GOVERNANCE_REVIEW_OPENED
from portable_runtime.governance.dispatch import (
    DISPATCH_COMMIT_EVENT,
    GovernanceDispatchCommitter,
)
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation, UseContext
from portable_runtime.governance.persistence import (
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
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


def _blocker(suffix: str) -> ReviewObligation:
    return ReviewObligation(
        id=f"q-e2b-{suffix}",
        target="d",
        trigger_ref=f"event-e2b-{suffix}",
        basis_refs=(f"basis-e2b-{suffix}",),
        context="ctx",
        blocking=True,
    )


def _request(suffix: str, *, work_id: str | None = None, run_id: str | None = None) -> CapabilityRequest:
    return CapabilityRequest(
        id=f"req-e2b-{suffix}",
        capability="test.read",
        work_id=work_id,
        run_id=run_id,
        idempotency_key=f"idem-e2b-{suffix}",
    )


def _permit(store: Any, request: CapabilityRequest) -> InvocationPermit:
    admission = GovernanceUseAdmission(store).evaluate(request, _requirement)
    assert admission.status == "allowed"
    assert admission.requirement_digest is not None
    assert admission.snapshot_digest is not None
    return InvocationPermit.issue(
        request,
        provider_id="e2b-provider",
        qualification_digest="",
        lease_generation=0,
        governance_applicable=True,
        governance_requirement_digest=admission.requirement_digest,
        governance_snapshot_digest=admission.snapshot_digest,
    )


def _dispatch_events(store: Any) -> list[Any]:
    return [event for event in store.list_events() if event.type == DISPATCH_COMMIT_EVENT]


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.reconcile_calls = 0
        self._descriptor = ProviderDescriptor(
            id="e2b-provider",
            name="E2b counting provider",
            version="1",
            capabilities=["test.read"],
            side_effect_class="pure",
            effect_semantics="pure",
            reversibility="reversible",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

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
        self.reconcile_calls += 1
        return CapabilityResult(
            request_id=request_id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )


def _boundary(store: Any, provider: _CountingProvider) -> RealityBoundary:
    registry = ProviderRegistry()
    registry.register(provider)
    return RealityBoundary(
        store=store,
        registry=registry,
        governance_requirement_resolver=_requirement,
    )


async def test_e2b_001_sqlite_blocker_commit_first_prevents_dispatch(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    db_path = tmp_path / "e2b-001.db"
    store_a = SQLiteStateStore(db_path)
    store_b = SQLiteStateStore(db_path)
    provider = _CountingProvider()
    try:
        SQLiteDistinctionGovernancePersistence(store_a).seed_state("d", _state())
        persistence_b = SQLiteDistinctionGovernancePersistence(store_b)
        real_committer = GovernanceDispatchCommitter

        class BlockerFirstCommitter:
            def __init__(self, store: Any) -> None:
                self.store = store

            def commit(self, *args: Any, **kwargs: Any) -> Any:
                persistence_b.open_obligation(_blocker("001"))
                return real_committer(self.store).commit(*args, **kwargs)

        monkeypatch.setattr(boundary_module, "GovernanceDispatchCommitter", BlockerFirstCommitter)
        result = await _boundary(store_a, provider).execute(_request("001"))

        assert persistence_b.get_obligation("q-e2b-001") is not None
        assert provider.calls == 0
        assert not _dispatch_events(store_a)
        assert result.error is not None
        assert result.error.get("code") == "GovernanceChanged"
    finally:
        store_b.close()
        store_a.close()


async def test_e2b_002_sqlite_dispatch_commit_first_survives_later_blocker(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    db_path = tmp_path / "e2b-002.db"
    store_a = SQLiteStateStore(db_path)
    store_b = SQLiteStateStore(db_path)
    provider = _CountingProvider()
    commit_refs: list[str] = []
    try:
        SQLiteDistinctionGovernancePersistence(store_a).seed_state("d", _state())
        persistence_b = SQLiteDistinctionGovernancePersistence(store_b)
        real_committer = GovernanceDispatchCommitter

        class DispatchFirstCommitter:
            def __init__(self, store: Any) -> None:
                self.store = store

            def commit(self, *args: Any, **kwargs: Any) -> Any:
                decision = real_committer(self.store).commit(*args, **kwargs)
                assert decision.status == "committed"
                assert decision.commit_ref is not None
                commit_refs.append(decision.commit_ref)
                persistence_b.open_obligation(_blocker("002"))
                return decision

        monkeypatch.setattr(boundary_module, "GovernanceDispatchCommitter", DispatchFirstCommitter)
        result = await _boundary(store_a, provider).execute(_request("002"))

        assert result.status == "succeeded"
        assert provider.calls == 1
        assert persistence_b.get_obligation("q-e2b-002") is not None
        assert len(commit_refs) == 1
        assert store_a.get_event(commit_refs[0]) is not None
    finally:
        store_b.close()
        store_a.close()


def test_e2b_003_memory_two_threads_observe_same_total_order() -> None:
    # blocker-first ordering
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state("d", _state())
    request = _request("003a")
    permit = _permit(store, request)
    blocker_done = threading.Event()
    first_result: list[Any] = []

    def block_first() -> None:
        persistence.open_obligation(_blocker("003a"))
        blocker_done.set()

    def dispatch_second() -> None:
        assert blocker_done.wait(timeout=5)
        first_result.append(
            GovernanceDispatchCommitter(store).commit(
                request,
                permit,
                _requirement,
                attempt_id=None,
            )
        )

    blocker_thread = threading.Thread(target=block_first, name="e2b-memory-blocker-first")
    dispatch_thread = threading.Thread(target=dispatch_second, name="e2b-memory-dispatch-second")
    blocker_thread.start()
    dispatch_thread.start()
    blocker_thread.join(timeout=5)
    dispatch_thread.join(timeout=5)
    assert not blocker_thread.is_alive() and not dispatch_thread.is_alive()
    assert len(first_result) == 1
    assert first_result[0].status == "blocked"
    assert not _dispatch_events(store)

    # dispatch-first ordering
    store2 = InMemoryStateStore()
    persistence2 = InMemoryDistinctionGovernancePersistence(store2)
    persistence2.seed_state("d", _state())
    request2 = _request("003b")
    permit2 = _permit(store2, request2)
    dispatch_done = threading.Event()
    second_result: list[Any] = []

    def dispatch_first() -> None:
        second_result.append(
            GovernanceDispatchCommitter(store2).commit(
                request2,
                permit2,
                _requirement,
                attempt_id=None,
            )
        )
        dispatch_done.set()

    def block_second() -> None:
        assert dispatch_done.wait(timeout=5)
        persistence2.open_obligation(_blocker("003b"))

    dispatch_thread2 = threading.Thread(target=dispatch_first, name="e2b-memory-dispatch-first")
    blocker_thread2 = threading.Thread(target=block_second, name="e2b-memory-blocker-second")
    dispatch_thread2.start()
    blocker_thread2.start()
    dispatch_thread2.join(timeout=5)
    blocker_thread2.join(timeout=5)
    assert not dispatch_thread2.is_alive() and not blocker_thread2.is_alive()
    assert len(second_result) == 1
    assert second_result[0].status == "committed"
    assert len(_dispatch_events(store2)) == 1
    assert persistence2.get_obligation("q-e2b-003b") is not None


def test_e2b_004_tampered_permit_binding_fails_closed() -> None:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    request = _request("004")
    permit = _permit(store, request)
    tampered = replace(permit, governance_snapshot_digest="0" * 64)

    decision = GovernanceDispatchCommitter(store).commit(
        request,
        tampered,
        _requirement,
        attempt_id=None,
    )

    assert decision.status == "changed"
    assert not _dispatch_events(store)


async def test_e2b_005_incompatible_history_at_commit_fails_before_provider(
    monkeypatch: Any,
) -> None:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    provider = _CountingProvider()
    real_committer = GovernanceDispatchCommitter

    class CorruptBeforeCommitter:
        def __init__(self, target_store: Any) -> None:
            self.store = target_store

        def commit(self, *args: Any, **kwargs: Any) -> Any:
            self.store.append_event(
                Event(
                    id="gov-e2b-005-future",
                    type=GOVERNANCE_REVIEW_OPENED,
                    subject_ref="d",
                    payload={
                        "schema_version": "distinction-governance-history-v999",
                        "contract_version": "distinction-governance-1.0",
                    },
                )
            )
            return real_committer(self.store).commit(*args, **kwargs)

    monkeypatch.setattr(boundary_module, "GovernanceDispatchCommitter", CorruptBeforeCommitter)
    result = await _boundary(store, provider).execute(_request("005"))

    assert provider.calls == 0
    assert not _dispatch_events(store)
    assert result.error is not None
    assert result.error.get("code") == "GovernanceUnavailable"


async def test_e2b_006_committed_attempt_survives_crash_as_recovery_fact() -> None:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    work = Work(id="work-e2b-006", title="E2b crash recovery")
    run = Run(id="run-e2b-006", work_id=work.id, status="running")
    step = Step(
        id="step-e2b-006",
        run_id=run.id,
        step_key="dispatch",
        status="running",
        effect_semantics="irreversible-opaque",
        side_effect_class="irreversible-opaque",
        reversibility="irreversible",
    )
    attempt = StepAttempt(
        id="attempt-e2b-006",
        step_id=step.id,
        provider_id="e2b-provider",
        request_ref="req-e2b-006",
        idempotency_key="idem-e2b-006",
        status="running",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    request = _request("006", work_id=work.id, run_id=run.id)
    permit = _permit(store, request)

    committed = GovernanceDispatchCommitter(store).commit(
        request,
        permit,
        _requirement,
        attempt_id=attempt.id,
    )
    assert committed.status == "committed"
    assert committed.commit_ref is not None
    persisted_attempt = store.get_attempt(attempt.id)
    assert persisted_attempt is not None
    assert persisted_attempt.metadata.get("dispatch_commit_ref") == committed.commit_ref
    assert persisted_attempt.metadata.get("invocation_permit_digest") == permit.request_digest

    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    recovered = await Runtime(store=store, registry=registry).reconcile(step.id)

    assert recovered is not None
    assert recovered.status == "unknown"
    assert "durably committed" in recovered.message
    assert provider.calls == 0
    assert provider.reconcile_calls == 0
    recovered_step = store.get_step(step.id)
    assert recovered_step is not None
    assert recovered_step.status == "unknown"
    assert store.get_event(committed.commit_ref) is not None


async def test_e2b_007_non_governed_invocation_preserves_existing_behavior() -> None:
    store = InMemoryStateStore()
    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)

    result = await RealityBoundary(store=store, registry=registry).execute(_request("007"))

    assert result.status == "succeeded"
    assert provider.calls == 1
    assert not _dispatch_events(store)


def test_e2b_008_commitment_binds_attempt_and_event_atomically() -> None:
    store = InMemoryStateStore()
    InMemoryDistinctionGovernancePersistence(store).seed_state("d", _state())
    work = Work(id="work-e2b-008", title="E2b atomic dispatch binding")
    run = Run(id="run-e2b-008", work_id=work.id, status="running")
    step = Step(
        id="step-e2b-008",
        run_id=run.id,
        step_key="dispatch",
        status="running",
        effect_semantics="idempotent",
        side_effect_class="idempotent",
    )
    attempt = StepAttempt(
        id="attempt-e2b-008",
        step_id=step.id,
        provider_id="e2b-provider",
        request_ref="req-e2b-008",
        idempotency_key="idem-e2b-008",
        status="running",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    request = _request("008", work_id=work.id, run_id=run.id)
    permit = _permit(store, request)

    decision = GovernanceDispatchCommitter(store).commit(
        request,
        permit,
        _requirement,
        attempt_id=attempt.id,
    )

    assert decision.status == "committed"
    assert decision.commit_ref is not None
    event = store.get_event(decision.commit_ref)
    rebound = store.get_attempt(attempt.id)
    assert event is not None
    assert rebound is not None
    assert event.payload["attempt_ref"] == attempt.id
    assert event.payload["invocation_permit_digest"] == permit.request_digest
    assert rebound.metadata["dispatch_commit_ref"] == decision.commit_ref
    assert rebound.metadata["governance_requirement_digest"] == permit.governance_requirement_digest
    assert rebound.metadata["governance_snapshot_digest"] == permit.governance_snapshot_digest
