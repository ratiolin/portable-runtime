from __future__ import annotations

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
from portable_runtime.governance.use_admission import GovernanceUseRequirement
from portable_runtime.stores.memory import InMemoryStateStore


class _GovernanceChangingProvider:
    def __init__(self, persistence: InMemoryDistinctionGovernancePersistence) -> None:
        self.calls = 0
        self._persistence = persistence
        self._opened = False
        self._descriptor = ProviderDescriptor(
            id="e2-provider",
            name="E2 governance-changing provider",
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
        if not self._opened:
            self._persistence.open_obligation(
                ReviewObligation(
                    id="q-e2-001",
                    target="d",
                    trigger_ref="event-e2-001",
                    basis_refs=("basis-e2",),
                    context="ctx",
                    blocking=True,
                )
            )
            self._opened = True
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


async def test_e2_001_new_blocking_q_after_initial_admission_stops_provider() -> None:
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

    provider = _GovernanceChangingProvider(persistence)
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(
        store=store,
        registry=registry,
        governance_requirement_resolver=lambda _request: GovernanceUseRequirement(
            scheme_id="d",
            use_context=UseContext("ctx", frozenset({"a"})),
        ),
    )

    result = await boundary.execute(
        CapabilityRequest(id="req-e2-001", capability="test.read")
    )

    assert provider.calls == 0
    assert result.error is not None
    assert result.error.get("code") == "GovernanceChanged"
