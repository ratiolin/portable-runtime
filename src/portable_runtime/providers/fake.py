from __future__ import annotations

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)


class EchoProvider:
    def __init__(self, provider_id: str = "echo", *, priority: int = 0) -> None:
        self._descriptor = ProviderDescriptor(
            id=provider_id,
            name="Echo Provider",
            version="1.0.0",
            capabilities=["text.echo"],
            priority=priority,
            tags={"side-effect-free"},
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message=request.instruction or "",
            metadata={"runtime_id": context.runtime_id},
        )

    async def cancel(self, request_id: str) -> None:
        return None


class FailingProvider(EchoProvider):
    def __init__(self, provider_id: str = "failing", *, capability: str = "text.echo") -> None:
        super().__init__(provider_id)
        self._descriptor = self._descriptor.model_copy(update={"capabilities": [capability]})

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        raise RuntimeError("provider failure")


