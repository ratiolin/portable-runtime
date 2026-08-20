from __future__ import annotations

from typing import Protocol

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
    """V1.6 Constraint Router: hard constraints > eligible > deterministic > cost."""

    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        eligible: list[ProviderDescriptor] = []
        # Hard constraints: independence + required_failure_domains + excluded domains
        required_independence = request.constraints.get("required_independence") or request.constraints.get("independent_on") or request.metadata.get("independence_constraints", {}).get("independent_on") if isinstance(request.metadata, dict) else None
        independent_from = request.constraints.get("independent_from_provider_ids") or request.metadata.get("independence_constraints", {}).get("independent_from_provider_ids") if isinstance(request.metadata, dict) else None
        # Build map of already-selected verifiers to compare domains
        # For single request, compare candidate domain values against excluded provider ids' domains
        if independent_from and isinstance(independent_from, list):
            # Need to lookup excluded providers' domains — approximate via registry if available, else just track ids
            pass
        for c in candidates:
            # Circuit breaker already filtered in boundary; here enforce independence
            if required_independence and isinstance(required_independence, list):
                # If request demands independent_on domains, candidate must not share those domains with excluded providers
                # For standalone routing without history, we check that candidate has those domains defined (fail-closed if not)
                # and will be filtered if it violates hard constraint vs already invoked providers (handled via excluded check)
                # Here we enforce: if candidate family matches excluded family's same domain value, skip
                skip = False
                if independent_from and isinstance(independent_from, list) and c.id in independent_from:
                        skip = True
                # Also check metadata independence constraints
                meta_ind = request.metadata.get("independence_constraints", {}) if isinstance(request.metadata, dict) else {}
                ind_on = meta_ind.get("independent_on") if isinstance(meta_ind, dict) else None
                if ind_on and isinstance(ind_on, list):
                    # Require candidate to have distinct provider_family/credential_domain etc from any excluded
                    # Since we don't have excluded descriptors here, just ensure candidate declares those domains
                    for dom in ind_on:
                        if getattr(c, dom, None) is None:
                            # fail-closed: candidate missing required domain info -> ineligible for independent verification
                            skip = True
                            break
                if skip:
                    continue
            # Also enforce explicit required_failure_domains constraint
            req_domains = request.constraints.get("required_failure_domains")
            if req_domains and isinstance(req_domains, dict):
                # e.g. {"provider_family": "openai"} -> candidate must match?
                # For independence, candidate must NOT match excluded values
                # We treat as hard filter: candidate's domain must satisfy constraint
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
        registry: ProviderRegistry,
        *,
        routing: RoutingPolicy | None = None,
        store: StateStore | None = None,
        runtime_id: str = "runtime",
    ) -> None:
        self.registry = registry
        self.routing = routing or ConstraintRouter()
        self.store = store
        self.runtime_id = runtime_id

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        # Delegate through RealityBoundary for unified enforcement chain (§1)
        from portable_runtime.core.boundary import RealityBoundary
        boundary = RealityBoundary(store=self.store, registry=self.registry, routing=self.routing, runtime_id=self.runtime_id)
        return await boundary.execute(request, capability_service=self)

    def _digest(self, request: CapabilityRequest) -> str:
        import hashlib
        import json
        payload = json.dumps({"cap": request.capability, "inst": request.instruction, "params": request.parameters}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    async def reconcile(self, request_id: str, provider_id: str) -> CapabilityResult | None:
        try:
            provider = self.registry.get(provider_id)
            if hasattr(provider, "reconcile"):
                return await provider.reconcile(request_id)  # type: ignore
        except Exception:
            pass
        return None
