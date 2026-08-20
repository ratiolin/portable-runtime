from __future__ import annotations

import builtins
from collections.abc import Iterable

from portable_runtime.core.capabilities import ProviderDescriptor, ProviderHealth
from portable_runtime.interfaces.provider import CapabilityProvider


class ProviderRegistry:
    """Runtime registry; provider lifecycle never owns canonical state."""

    def __init__(self) -> None:
        self._providers: dict[str, CapabilityProvider] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, provider: CapabilityProvider, _maybe_provider: CapabilityProvider | None = None) -> ProviderDescriptor:
        # Back-compat: test harness calls register(descriptor, provider); support both forms
        if _maybe_provider is not None:
            provider = _maybe_provider
        descriptor = provider.descriptor
        if descriptor.id in self._providers:
            raise ValueError(f"provider already registered: {descriptor.id}")
        self._providers[descriptor.id] = provider
        self._enabled[descriptor.id] = descriptor.enabled
        return self._descriptor(descriptor.id)

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
        self._enabled.pop(provider_id, None)

    def enable(self, provider_id: str) -> ProviderDescriptor:
        self._require(provider_id)
        self._enabled[provider_id] = True
        return self._descriptor(provider_id)

    def disable(self, provider_id: str) -> ProviderDescriptor:
        self._require(provider_id)
        self._enabled[provider_id] = False
        return self._descriptor(provider_id)

    def reload(self, provider_id: str) -> ProviderDescriptor:
        self._require(provider_id)
        # In-process providers are already live. External managers can replace
        # the object and then call unregister/register without changing state.
        return self._descriptor(provider_id)

    def get(self, provider_id: str) -> CapabilityProvider:
        return self._providers[provider_id]

    def list_descriptors(self) -> builtins.list[ProviderDescriptor]:
        return [self._descriptor(provider_id) for provider_id in sorted(self._providers)]

    def list(self) -> builtins.list[ProviderDescriptor]:
        return self.list_descriptors()

    def providers_for(self, capability: str) -> builtins.list[ProviderDescriptor]:
        return [
            descriptor
            for descriptor in self.list_descriptors()
            if descriptor.enabled and capability in descriptor.capabilities
        ]

    async def health(self, provider_id: str) -> ProviderHealth:
        provider = self.get(provider_id)
        try:
            result = await provider.health()
        except Exception as exc:  # provider failures must not crash the runtime
            return ProviderHealth(provider_id=provider_id, available=False, detail=str(exc))
        if not self._enabled.get(provider_id, False):
            return result.model_copy(update={"available": False, "detail": "disabled"})
        return result

    def descriptors_for(self, capability: str, excluded: Iterable[str] = ()) -> builtins.list[ProviderDescriptor]:
        excluded_set = set(excluded)
        return [
            descriptor
            for descriptor in self.providers_for(capability)
            if descriptor.id not in excluded_set
        ]

    def _descriptor(self, provider_id: str) -> ProviderDescriptor:
        descriptor = self._providers[provider_id].descriptor
        return descriptor.model_copy(update={"enabled": self._enabled.get(provider_id, False)})

    def _require(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise KeyError(f"unknown provider: {provider_id}")
