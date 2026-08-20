"""Workflow context bridging Runtime and providers (portable, provider-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass

from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
from portable_runtime.core.models import Run, Work
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.interfaces.store import StateStore


@dataclass(slots=True)
class WorkflowContext:
    work: Work
    run: Run
    store: StateStore
    capabilities: CapabilityService
    registry: ProviderRegistry

    async def invoke(
        self, capability: str, *, instruction: str | None = None, **parameters: object
    ) -> CapabilityResult:
        req = CapabilityRequest(
            id=f"req_{self.run.id}_{capability}",
            capability=capability,
            work_id=self.work.id,
            run_id=self.run.id,
            instruction=instruction,
            parameters=dict(parameters),
        )
        return await self.capabilities.invoke(req)
