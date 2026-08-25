from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation, UseContext
from portable_runtime.governance.persistence import SQLiteDistinctionGovernancePersistence
from portable_runtime.governance.use_admission import GovernanceUseRequirement
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


def _blocker() -> ReviewObligation:
    return ReviewObligation(
        id="q-e2b-001",
        target="d",
        trigger_ref="event-e2b-001",
        basis_refs=("basis-e2b-001",),
        context="ctx",
        blocking=True,
    )


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
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
        del request_id
        return None


class _InvocationStartedBarrierStore(SQLiteStateStore):
    """Test-only barrier after E2a final recheck and before provider.invoke()."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.invocation_started = threading.Event()
        self.release_invocation_started = threading.Event()
        self._barrier_used = False

    def append_event(self, value: Any) -> None:
        if getattr(value, "type", "") == "InvocationStarted" and not self._barrier_used:
            self._barrier_used = True
            self.invocation_started.set()
            if not self.release_invocation_started.wait(timeout=5):
                raise TimeoutError("E2b invocation-started barrier timed out")
        super().append_event(value)


async def test_e2b_001_blocker_commit_before_dispatch_commitment_prevents_provider(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "e2b-001.db"
    store_a = _InvocationStartedBarrierStore(db_path)
    store_b = SQLiteStateStore(db_path)
    errors: list[BaseException] = []
    provider = _CountingProvider()
    try:
        persistence_a = SQLiteDistinctionGovernancePersistence(store_a)
        persistence_b = SQLiteDistinctionGovernancePersistence(store_b)
        persistence_a.seed_state("d", _state())

        def commit_blocker() -> None:
            try:
                if not store_a.invocation_started.wait(timeout=5):
                    raise TimeoutError("Boundary did not reach pre-dispatch barrier")
                persistence_b.open_obligation(_blocker())
            except BaseException as exc:
                errors.append(exc)
            finally:
                store_a.release_invocation_started.set()

        worker = threading.Thread(target=commit_blocker, name="e2b-001-blocker")
        worker.start()

        registry = ProviderRegistry()
        registry.register(provider)
        result = await RealityBoundary(
            store=store_a,
            registry=registry,
            governance_requirement_resolver=_requirement,
        ).execute(CapabilityRequest(id="req-e2b-001", capability="test.read"))
        worker.join(timeout=5)

        assert not worker.is_alive()
        assert not errors
        assert persistence_b.get_obligation("q-e2b-001") is not None
        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceChanged"
    finally:
        store_b.close()
        store_a.close()
