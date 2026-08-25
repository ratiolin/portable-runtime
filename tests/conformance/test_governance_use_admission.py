from __future__ import annotations

from dataclasses import dataclass

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
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.stores.memory import InMemoryStateStore


@dataclass(frozen=True)
class _GovernanceUseRequirement:
    scheme_id: str
    use_context: UseContext


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self._descriptor = ProviderDescriptor(
            id="e1-provider",
            name="E1 counting provider",
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
        self.calls += 1
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="invoked",
        )

    async def cancel(self, request_id: str) -> None:
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        return None


def _clear_memory_sidecar(store: InMemoryStateStore) -> None:
    records = vars(store)["_distinction_governance_records"]
    for values in records.values():
        values.clear()


async def test_e1_001_canonical_blocker_with_empty_sidecar_stops_provider() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state(
        "d",
        DistinctionState(
            qualification="qualified",
            activation="active",
            scope=frozenset({"a"}),
            partition=(frozenset({"a"}),),
            version=1,
        ),
    )
    persistence.open_obligation(
        ReviewObligation(
            id="q-e1-001",
            target="d",
            trigger_ref="event-e1-001",
            basis_refs=("basis-e1",),
            context="ctx",
            blocking=True,
        )
    )

    # Canonical events remain; the private materialized projection is absent.
    _clear_memory_sidecar(store)
    assert persistence.list_states() == {}
    assert persistence.list_obligations() == {}
    assert any(
        event.type.startswith("governance.distinction.")
        for event in store.list_events()
    )

    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry)

    # Runtime-owned fixture. The current Boundary intentionally has no E1 seam
    # yet and will ignore this resolver, exposing the bypass.
    boundary.governance_requirement_resolver = (
        lambda _request: _GovernanceUseRequirement(
            scheme_id="d",
            use_context=UseContext("ctx", frozenset({"a"})),
        )
    )

    result = await boundary.execute(
        CapabilityRequest(id="req-e1-001", capability="test.read")
    )

    assert provider.calls == 0
    assert result.error is not None
    assert result.error.get("code") == "GovernanceBlocked"
