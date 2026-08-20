from __future__ import annotations

from typing import Protocol

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)


class CapabilityProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    async def health(self) -> ProviderHealth: ...

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult: ...

    async def cancel(self, request_id: str) -> None: ...
