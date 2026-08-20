from __future__ import annotations

from typing import Protocol

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
)
from portable_runtime.core.models import Action, Outcome, Step, StepAttempt, new_id, utcnow
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.reliability import CircuitBreaker
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


class ConstraintRouter(DeterministicPriorityRouting):
    """V1.6 Constraint Router: hard constraints > eligible > deterministic > cost."""

    async def select(
        self,
        request: CapabilityRequest,
        candidates: list[ProviderDescriptor],
    ) -> ProviderDescriptor | None:
        # Filter by hard policy constraints expressed in request.constraints
        # e.g., required_failure_domains, required_capabilities
        eligible = []
        for c in candidates:
            # Check required failure domain independence
            required = request.constraints.get("required_independence")
            if required:
                # candidate must have distinct domains for listed keys
                # This is a placeholder check: in real routing, compare against already-selected verifiers
                pass
            eligible.append(c)
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
        # V1.1 Step tracking for effect semantics
        step_id = None
        if self.store is not None and request.work_id and request.run_id:
            # Create or update Step for fencing/idempotency
            step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
            # Try to find existing step by key
            existing_steps = []
            try:
                existing_steps = self.store.list_steps(request.run_id)  # type: ignore
            except Exception:
                pass
            step = next((s for s in existing_steps if s.step_key == step_key), None)
            if step is None:
                step = Step(
                    id=new_id("step"),
                    run_id=request.run_id,
                    step_key=step_key,
                    kind=request.capability.split(".")[0] if "." in request.capability else "generic",
                    status="running",
                    effect_semantics=selected.effect_semantics if hasattr(selected, "effect_semantics") else "pure",
                    side_effect_class=selected.side_effect_class if hasattr(selected, "side_effect_class") else "pure",
                    reversibility=selected.reversibility if hasattr(selected, "reversibility") else "unknown",
                    input_digest=self._digest(request),
                )
                try:
                    self.store.save_step(step)  # type: ignore
                except Exception:
                    pass
                step_id = step.id
            else:
                step.status = "running"
                step.updated_at = utcnow()
                step.version = (step.version or 0) + 1
                try:
                    self.store.save_step(step)  # type: ignore
                except Exception:
                    pass
                step_id = step.id
            # Create attempt
            attempt = StepAttempt(
                id=new_id("attempt"),
                step_id=step_id,
                attempt_no=(step.current_attempt or 0) + 1,
                provider_id=selected.id,
                request_ref=request.id,
                idempotency_key=request.idempotency_key or request.id,
                status="running",
                lease_generation=getattr(request, "metadata", {}).get("lease_generation", 0) if hasattr(request, "metadata") else 0,
            )
            step.current_attempt = attempt.attempt_no
            try:
                self.store.save_step(step)  # type: ignore
                self.store.save_attempt(attempt)  # type: ignore
            except Exception:
                pass
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
            lease_generation=getattr(request, "metadata", {}).get("lease_generation", 0) if hasattr(request, "metadata") and isinstance(request.metadata, dict) else 0,
            idempotency_key=request.idempotency_key,
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
        # Update step/attempt with result
        if self.store is not None and request.work_id and request.run_id and step_id:
            try:
                step = self.store.get_step(step_id)  # type: ignore
                if step:
                    if result.status == "succeeded":
                        step.status = "succeeded"
                    elif result.status == "failed":
                        step.status = "failed"
                    elif result.status == "unknown":
                        step.status = "unknown"
                    elif result.status in ("cancelled", "unavailable"):
                        step.status = "failed"
                    step.updated_at = utcnow()
                    self.store.save_step(step)  # type: ignore
                # update last attempt
                attempts = self.store.list_attempts(step_id)  # type: ignore
                if attempts:
                    last = sorted(attempts, key=lambda a: a.attempt_no)[-1]
                    last.status = result.status if result.status in ("succeeded", "failed", "cancelled", "unknown") else "failed"
                    last.ended_at = utcnow()
                    last.result_ref = result.request_id
                    if result.error:
                        last.error = result.error
                    self.store.save_attempt(last)  # type: ignore
            except Exception:
                pass
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


