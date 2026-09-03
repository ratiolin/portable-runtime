from __future__ import annotations

from typing import Any, Protocol

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    ProviderDescriptor,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.reliability import CircuitBreaker
from portable_runtime.interfaces.store import StateStore


class RoutingPolicy(Protocol):
    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None: ...


class DeterministicPriorityRouting:
    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        if not candidates:
            return None
        preferred = {
            provider_id: index
            for index, provider_id in enumerate(request.preferred_provider_ids)
        }
        hard_constraints = {
            key: value
            for key, value in request.constraints.items()
            if key not in {"required_failure_domains", "independence_constraints"}
        }
        matching = [
            descriptor
            for descriptor in candidates
            if all(
                descriptor.constraints.get(key) == value
                for key, value in hard_constraints.items()
            )
        ]
        if not matching:
            return None
        return sorted(
            matching,
            key=lambda descriptor: (
                preferred.get(descriptor.id, len(preferred)),
                -descriptor.priority,
                descriptor.id,
            ),
        )[0]


class ConstraintRouter(DeterministicPriorityRouting):
    """Apply hard constraints and deterministic provider selection."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry

    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        from portable_runtime.core.independence import IndependenceContext

        independence = IndependenceContext.from_request(request)
        reference_descriptors: list[ProviderDescriptor] = []
        if (
            independence
            and independence.reference_provider_refs
            and independence.independent_on
            and self.registry is not None
        ):
            descriptors_by_id = {
                descriptor.id: descriptor
                for descriptor in self.registry.list_descriptors()
            }
            reference_descriptors = [
                descriptors_by_id[provider_id]
                for provider_id in independence.reference_provider_refs
                if provider_id in descriptors_by_id
            ]

        eligible: list[ProviderDescriptor] = []
        for candidate in candidates:
            if independence and independence.independent_on and reference_descriptors:
                satisfied, _ = independence.is_satisfied(
                    candidate, reference_descriptors
                )
                if not satisfied:
                    continue
            elif independence and independence.independent_on:
                if any(
                    getattr(candidate, domain, None) is None
                    for domain in independence.independent_on
                ):
                    continue
                if independence.reference_provider_refs:
                    continue

            required_domains = request.constraints.get("required_failure_domains")
            if isinstance(required_domains, dict) and not all(
                getattr(candidate, key, None) == value
                for key, value in required_domains.items()
            ):
                continue
            eligible.append(candidate)

        return await super().select(request, eligible)


_CIRCUITS: dict[str, CircuitBreaker] = {}


def _circuit_for(provider_id: str) -> CircuitBreaker:
    if provider_id not in _CIRCUITS:
        _CIRCUITS[provider_id] = CircuitBreaker()
    return _CIRCUITS[provider_id]


class CapabilityService:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        routing: RoutingPolicy | None = None,
        store: StateStore | None = None,
        runtime_id: str = "runtime",
        boundary: Any | None = None,
        **_kwargs: Any,
    ) -> None:
        if boundary is not None:
            self.boundary = boundary
            self.registry = boundary.registry
            self.routing = boundary.routing
            self.store = boundary.store
            self.runtime_id = boundary.runtime_id
            if hasattr(self.routing, "registry"):
                self.routing.registry = self.registry
            return

        if registry is None:
            raise TypeError("CapabilityService requires either registry or boundary")

        from portable_runtime.core.boundary import RealityBoundary
        from portable_runtime.core.capability_contract import CapabilityContractRegistry

        self.registry = registry
        self.routing = routing or ConstraintRouter(registry=registry)
        if hasattr(self.routing, "registry"):
            self.routing.registry = registry
        self.store = store
        self.runtime_id = runtime_id
        self.boundary = RealityBoundary(
            store=store,
            registry=registry,
            routing=self.routing,
            runtime_id=runtime_id,
            contract_registry=CapabilityContractRegistry(),
        )

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        return await self.boundary.execute(request, capability_service=self)

    async def reconcile(
        self, request_id: str, provider_id: str
    ) -> CapabilityResult | None:
        return await self.boundary.reconcile(
            request_id,
            provider_id,
            capability_service=self,
        )
