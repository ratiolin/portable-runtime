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
        # ``required_failure_domains`` and independence are evaluated below
        # by the typed router; they are not ordinary descriptor key/value
        # constraints and must not make every otherwise eligible provider
        # disappear during deterministic tie-breaking.
        hard_constraints = {
            key: value
            for key, value in request.constraints.items()
            if key not in {"required_failure_domains", "independence_constraints"}
        }
        matching = [
            descriptor
            for descriptor in candidates
            if all(descriptor.constraints.get(key) == value for key, value in hard_constraints.items())
        ]
        if not hard_constraints:
            matching = candidates
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
    """R1.6 Constraint Router: hard constraints > eligible > deterministic > cost."""

    def __init__(self, registry: Any | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[call-arg]
        self.registry: Any | None = registry

    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        from portable_runtime.core.independence import IndependenceContext  # type: ignore[import-untyped]

        ind_ctx = IndependenceContext.from_request(request)
        reference_descriptors: list[ProviderDescriptor] = []
        if ind_ctx and ind_ctx.reference_provider_refs and ind_ctx.independent_on:
            reg = getattr(self, "registry", None)
            if reg is not None:
                for ref_id in ind_ctx.reference_provider_refs:
                    try:
                        prov = reg.get(ref_id)  # type: ignore
                        reference_descriptors.append(prov.descriptor)  # type: ignore
                    except Exception:
                        try:
                            for d in reg.list_descriptors():  # type: ignore
                                if d.id == ref_id:
                                    reference_descriptors.append(d)
                                    break
                        except Exception:
                            pass
            else:
                # Provider descriptors are authoritative registry state.  A
                # caller-supplied ``reference_descriptors`` payload is only a
                # proof-shaped hint and must never establish independence.
                # Leave the reference set empty so the fail-closed branch
                # below marks every candidate ineligible when refs are
                # required but the registry cannot resolve them.
                reference_descriptors = []
        eligible: list[ProviderDescriptor] = []
        for c in candidates:
            if ind_ctx and ind_ctx.independent_on and reference_descriptors:
                ok, _ = ind_ctx.is_satisfied(c, reference_descriptors)
                if not ok:
                    continue
            elif ind_ctx and ind_ctx.independent_on:
                skip = False
                for dom in ind_ctx.independent_on:
                    if getattr(c, dom, None) is None:
                        skip = True
                        break
                if skip:
                    continue
                if ind_ctx.reference_provider_refs:
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
        **_kwargs: Any,
    ) -> None:
        if boundary is not None:
            self.boundary = boundary
            self.registry = getattr(boundary, "registry", registry) or registry  # type: ignore
            self.routing = getattr(boundary, "routing", routing or ConstraintRouter(registry=self.registry))  # type: ignore
            self.store = getattr(boundary, "store", store)
            self.runtime_id = getattr(boundary, "runtime_id", runtime_id)
            try:
                if hasattr(self.routing, "registry"):
                    self.routing.registry = self.registry  # type: ignore
            except Exception:
                pass
            return
        if registry is None:
            raise TypeError("CapabilityService requires either registry or boundary")
        self.registry = registry
        self.routing = routing or ConstraintRouter(registry=registry)
        try:
            if hasattr(self.routing, "registry"):
                self.routing.registry = registry  # type: ignore
        except Exception:
            pass
        self.store = store
        self.runtime_id = runtime_id
        try:
            from portable_runtime.core.boundary import RealityBoundary
            from portable_runtime.core.capability_contract import CapabilityContractRegistry
            self.boundary = RealityBoundary(  # type: ignore
                store=self.store,
                registry=self.registry,
                routing=self.routing,
                runtime_id=self.runtime_id,
                contract_registry=CapabilityContractRegistry(),
            )
        except Exception:
            self.boundary = None  # type: ignore

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        if hasattr(self, "boundary") and self.boundary is not None:
            return await self.boundary.execute(request, capability_service=self)  # type: ignore
        from portable_runtime.core.boundary import RealityBoundary
        boundary = RealityBoundary(store=self.store, registry=self.registry, routing=self.routing, runtime_id=self.runtime_id)
        return await boundary.execute(request, capability_service=self)

    async def reconcile(self, request_id: str, provider_id: str) -> CapabilityResult | None:
        """Route recovery reconciliation through the RealityBoundary.

        Recovery is still an authority-sensitive runtime action.  Keeping the
        provider call behind the boundary prevents ``Runtime`` or a workflow
        from bypassing the single reality exit.
        """

        boundary = getattr(self, "boundary", None)
        if boundary is None:
            from portable_runtime.core.boundary import RealityBoundary

            boundary = RealityBoundary(
                store=self.store,
                registry=self.registry,
                routing=self.routing,
                runtime_id=self.runtime_id,
            )
        reconcile = getattr(boundary, "reconcile", None)
        if reconcile is None:
            return None
        return await reconcile(request_id, provider_id, capability_service=self)

    def _digest(self, request: CapabilityRequest) -> str:
        import hashlib
        import json
        payload = json.dumps({"cap": request.capability, "inst": request.instruction, "params": request.parameters}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
