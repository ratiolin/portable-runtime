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
        preferred = {provider_id: index for index, provider_id in enumerate(request.preferred_provider_ids)}
        matching = [
            descriptor
            for descriptor in candidates
            if all(descriptor.constraints.get(key) == value for key, value in request.constraints.items())
        ]
        if not request.constraints:
            matching = candidates
        return sorted(
            matching,
            key=lambda descriptor: (
                preferred.get(descriptor.id, len(preferred)),
                -descriptor.priority,
                descriptor.id,
            ),
        )[0]

class ConstraintRouter(DeterministicPriorityRouting):
    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        eligible: list[ProviderDescriptor] = []
        required_independence = request.constraints.get("required_independence") or request.constraints.get("independent_on") or request.metadata.get("independence_constraints", {}).get("independent_on") if isinstance(request.metadata, dict) else None
        independent_from = request.constraints.get("independent_from_provider_ids") or request.metadata.get("independence_constraints", {}).get("independent_from_provider_ids") if isinstance(request.metadata, dict) else None
        for c in candidates:
            if required_independence and isinstance(required_independence, list):
                skip = False
                if independent_from and isinstance(independent_from, list) and c.id in independent_from:
                    skip = True
                meta_ind = request.metadata.get("independence_constraints", {}) if isinstance(request.metadata, dict) else {}
                ind_on = meta_ind.get("independent_on") if isinstance(meta_ind, dict) else None
                if ind_on and isinstance(ind_on, list):
                    for dom in ind_on:
                        if getattr(c, dom, None) is None:
                            skip = True
                            break
                if skip:
                    continue
            req_domains = request.constraints.get("required_failure_domains")
            if req_domains and isinstance(req_domains, dict):
                ok = True
                for k, v in req_domains.items():
                    if getattr(c, k, None) != v:
                        ok = False
                        break
                if not ok:
                    continue
            eligible.append(c)
        if not eligible:
            return None
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
    ) -> None:
        from portable_runtime.core.boundary import RealityBoundary  # type: ignore
        from portable_runtime.core.capability_contract import CapabilityContractRegistry  # type: ignore
        if boundary is not None:
            self.boundary = boundary
            self.registry = getattr(boundary, "registry", registry) or registry  # type: ignore
            self.routing = getattr(boundary, "routing", routing or ConstraintRouter())  # type: ignore
            self.store = getattr(boundary, "store", store)
            self.runtime_id = getattr(boundary, "runtime_id", runtime_id)
        else:
            self.registry = registry  # type: ignore
            self.routing = routing or ConstraintRouter()
            self.store = store
            self.runtime_id = runtime_id
            self.boundary = RealityBoundary(  # type: ignore
                store=self.store,
                registry=self.registry,
                routing=self.routing,
                runtime_id=self.runtime_id,
                contract_registry=CapabilityContractRegistry(),
            )

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        return await self.boundary.execute(request)  # type: ignore

    def _digest(self, request: CapabilityRequest) -> str:
        import hashlib
        import json
        payload = json.dumps({"cap": request.capability, "inst": request.instruction, "params": request.parameters}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    async def reconcile(self, request_id: str, provider_id: str) -> CapabilityResult | None:
        try:
            provider = self.registry.get(provider_id)  # type: ignore[union-attr]
            if hasattr(provider, "reconcile"):
                return await provider.reconcile(request_id)  # type: ignore
        except Exception:
            pass
        return None
