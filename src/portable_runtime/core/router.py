from __future__ import annotations

from typing import Protocol

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
)
from portable_runtime.core.models import Action, Outcome, new_id
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.interfaces.provider import CapabilityProvider
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
        self.routing = routing or DeterministicPriorityRouting()
        self.store = store
        self.runtime_id = runtime_id

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        descriptors = self.registry.descriptors_for(request.capability, request.excluded_provider_ids)
        healthy: list[ProviderDescriptor] = []
        for descriptor in descriptors:
            health = await self.registry.health(descriptor.id)
            if health.available:
                healthy.append(descriptor)
        selected = await self.routing.select(request, healthy)
        if selected is None:
            return CapabilityResult(
                request_id=request.id,
                provider_id="",
                status="unavailable",
                message=f"capability unavailable: {request.capability}",
            )
        provider: CapabilityProvider = self.registry.get(selected.id)
        action_id = new_id("action")
        if self.store is not None and request.work_id and request.run_id:
            self.store.save_action(
                Action(
                    id=action_id,
                    work_id=request.work_id,
                    run_id=request.run_id,
                    capability=request.capability,
                    provider_id=selected.id,
                    request_ref=request.id,
                    status="running",
                )
            )
        context = InvocationContext(
            runtime_id=self.runtime_id,
            work_id=request.work_id,
            run_id=request.run_id,
        )
        try:
            result = await provider.invoke(request, context)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            result = CapabilityResult(
                request_id=request.id,
                provider_id=selected.id,
                status="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        if self.store is not None and request.work_id and request.run_id:
            self.store.save_action(
                Action(
                    id=action_id,
                    work_id=request.work_id,
                    run_id=request.run_id,
                    capability=request.capability,
                    provider_id=selected.id,
                    request_ref=request.id,
                    status=result.status,
                )
            )
            self.store.save_outcome(
                Outcome(
                    id=new_id("outcome"),
                    action_id=action_id,
                    artifact_refs=result.output_artifact_refs,
                    evidence_refs=result.evidence_refs,
                    status=result.status,
                )
            )
        return result
