from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)


class FunctionProvider:
    def __init__(
        self,
        handler: Callable[[CapabilityRequest, InvocationContext], Awaitable[CapabilityResult]],
        *,
        provider_id: str,
        version: str,
        capabilities: list[str],
        name: str | None = None,
    ) -> None:
        self._handler = handler
        self._descriptor = ProviderDescriptor(
            id=provider_id,
            name=name or provider_id,
            version=version,
            capabilities=capabilities,
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        return await self._handler(request, context)

    async def cancel(self, request_id: str) -> None:
        return None


def provider(
    *,
    id: str,
    version: str,
    capabilities: list[str],
    name: str | None = None,
) -> Callable[[Callable[..., Any]], FunctionProvider]:
    """Turn a small async handler into a conformance-compatible provider."""

    def decorate(handler: Callable[..., Any]) -> FunctionProvider:
        async def invoke(request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
            if len(inspect.signature(handler).parameters) == 1:
                result = await handler(request)
            else:
                result = await handler(request, context)
            if isinstance(result, CapabilityResult):
                return result
            return CapabilityResult(
                request_id=request.id,
                provider_id=id,
                status="succeeded",
                message=str(result),
            )

        return FunctionProvider(
            invoke,
            provider_id=id,
            version=version,
            capabilities=capabilities,
            name=name,
        )

    return decorate
