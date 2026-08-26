from __future__ import annotations

import builtins
import uuid
from collections.abc import Iterable
from contextlib import suppress

from portable_runtime.core.capabilities import ProviderDescriptor, ProviderHealth
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    build_provider_execution_binding,
    provider_execution_descriptor_digest,
)
from portable_runtime.interfaces.provider import CapabilityProvider


class ProviderRegistry:
    """Runtime registry; provider lifecycle never owns canonical state.

    The registry is the authoritative configured-provider path for the current
    runtime. Each live registration receives an exact ProviderExecutionBinding.
    Callers that need cross-process resolvability must supply the same stable
    configured execution identity and authoritative configuration reference on
    each registration. Omitting them creates a registration-incarnation
    identity that is exact for this registration but intentionally cannot be
    reconstructed from a future registry by provider id or descriptor alone.
    """

    def __init__(self) -> None:
        self._providers: dict[str, CapabilityProvider] = {}
        self._enabled: dict[str, bool] = {}
        self._execution_bindings: dict[str, ProviderExecutionBinding] = {}

    def register(
        self,
        provider: CapabilityProvider,
        _maybe_provider: CapabilityProvider | None = None,
        *,
        configured_execution_identity: str | None = None,
        authoritative_configuration_ref: str | None = None,
    ) -> ProviderDescriptor:
        # Back-compat: test harness calls register(descriptor, provider); support both forms.
        if _maybe_provider is not None:
            provider = _maybe_provider
        descriptor = provider.descriptor
        if descriptor.id in self._providers:
            raise ValueError(f"provider already registered: {descriptor.id}")
        if (configured_execution_identity is None) != (authoritative_configuration_ref is None):
            raise ValueError(
                "stable configured-provider registration requires both execution identity and configuration ref"
            )
        if configured_execution_identity is None:
            incarnation = uuid.uuid4().hex
            configured_execution_identity = f"provider-registration:{descriptor.id}:{incarnation}"
            authoritative_configuration_ref = f"runtime-registration:{incarnation}"
        assert authoritative_configuration_ref is not None
        binding = build_provider_execution_binding(
            descriptor,
            configured_execution_identity=configured_execution_identity,
            authoritative_configuration_ref=authoritative_configuration_ref,
        )
        # Circuit state belongs to a live provider registration, not merely to
        # a string id. Test/runtime registries may intentionally replace a
        # provider with the same id after a prior failure; carrying an open
        # breaker across that replacement would make an unrelated provider
        # permanently ineligible.
        with suppress(Exception):
            from portable_runtime.core.boundary import _CIRCUITS

            _CIRCUITS.pop(descriptor.id, None)
        self._providers[descriptor.id] = provider
        self._enabled[descriptor.id] = descriptor.enabled
        self._execution_bindings[descriptor.id] = binding
        return self._descriptor(descriptor.id)

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
        self._enabled.pop(provider_id, None)
        self._execution_bindings.pop(provider_id, None)

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

    def execution_binding(self, provider_id: str) -> ProviderExecutionBinding:
        """Return the exact current binding; descriptor drift fails closed."""

        self._require(provider_id)
        binding = self._execution_bindings[provider_id]
        current_digest = provider_execution_descriptor_digest(
            self._providers[provider_id].descriptor
        )
        if binding.descriptor_digest != current_digest:
            raise ValueError(
                f"configured provider descriptor drift for {provider_id!r}; re-register provider explicitly"
            )
        return binding

    def resolve_execution_binding(
        self,
        historical: ProviderExecutionBinding,
    ) -> CapabilityProvider | None:
        """Resolve only an exact current configured identity; never retarget by provider id."""

        if historical.provider_id not in self._providers:
            return None
        try:
            current = self.execution_binding(historical.provider_id)
        except (KeyError, ValueError):
            return None
        if current != historical:
            return None
        return self._providers[historical.provider_id]

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
