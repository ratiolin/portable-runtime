from __future__ import annotations

import builtins
import contextvars
import threading
import uuid
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass

from portable_runtime.core.capabilities import ProviderDescriptor, ProviderHealth
from portable_runtime.core.reconciliation_repeatability import (
    ReconciliationRepeatabilityAuthority,
    ReconciliationRepeatabilityConfiguration,
    ReconciliationRepeatabilityContract,
    ReconciliationRepeatabilityEligibility,
    build_reconciliation_repeatability_authority,
    build_reconciliation_repeatability_contract,
    evaluate_reconciliation_repeatability,
)
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    build_provider_execution_binding,
    provider_execution_descriptor_digest,
)
from portable_runtime.interfaces.provider import CapabilityProvider


@dataclass(frozen=True)
class _ExecutionLookup:
    registry: ProviderRegistry
    provider_id: str
    provider: CapabilityProvider


_execution_lookup: contextvars.ContextVar[_ExecutionLookup | None] = contextvars.ContextVar(
    "portable_runtime_provider_execution_lookup",
    default=None,
)


def consume_execution_target_lookup(
    provider_id: str,
) -> tuple[ProviderRegistry, CapabilityProvider] | None:
    """Consume the task-local provider object fetched for the reality-exit path."""

    lookup = _execution_lookup.get()
    _execution_lookup.set(None)
    if lookup is None or lookup.provider_id != provider_id:
        return None
    return lookup.registry, lookup.provider


class ProviderRegistry:
    """Runtime registry; provider lifecycle never owns canonical state.

    The registry is the authoritative configured-provider path for the current
    runtime. Each live registration receives an exact ProviderExecutionBinding.
    Callers that need cross-process resolvability must supply the same stable
    configured execution identity and authoritative configuration reference on
    each registration. Omitting them creates a registration-incarnation
    identity that is exact for this registration but intentionally cannot be
    reconstructed from a future registry by provider id or descriptor alone.

    Optional reconciliation repeatability configuration is a separate
    responsibility domain. It is bound to the exact ProviderExecutionBinding at
    registration and does not modify ProviderDescriptor execution semantics.
    Only an explicit repeat-safe configured contract can later be instantiated
    as exact request-id historical repeatability authority at governed dispatch.
    """

    def __init__(self) -> None:
        self._providers: dict[str, CapabilityProvider] = {}
        self._enabled: dict[str, bool] = {}
        self._execution_bindings: dict[str, ProviderExecutionBinding] = {}
        self._reconciliation_repeatability_contracts: dict[
            str, ReconciliationRepeatabilityContract
        ] = {}
        self._lock = threading.RLock()

    def register(
        self,
        provider: CapabilityProvider,
        _maybe_provider: CapabilityProvider | None = None,
        *,
        configured_execution_identity: str | None = None,
        authoritative_configuration_ref: str | None = None,
        reconciliation_repeatability: ReconciliationRepeatabilityConfiguration | None = None,
    ) -> ProviderDescriptor:
        # Back-compat: test harness calls register(descriptor, provider); support both forms.
        if _maybe_provider is not None:
            provider = _maybe_provider
        descriptor = provider.descriptor
        with self._lock:
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
            if authoritative_configuration_ref is None:
                raise ValueError("provider registration configuration ref is unavailable")
            binding = build_provider_execution_binding(
                descriptor,
                configured_execution_identity=configured_execution_identity,
                authoritative_configuration_ref=authoritative_configuration_ref,
            )
            repeatability_contract = (
                build_reconciliation_repeatability_contract(binding, reconciliation_repeatability)
                if reconciliation_repeatability is not None
                else None
            )
            with suppress(Exception):
                from portable_runtime.core.boundary import _CIRCUITS

                _CIRCUITS.pop(descriptor.id, None)
            self._providers[descriptor.id] = provider
            self._enabled[descriptor.id] = descriptor.enabled
            self._execution_bindings[descriptor.id] = binding
            if repeatability_contract is not None:
                self._reconciliation_repeatability_contracts[descriptor.id] = repeatability_contract
            return self._descriptor(descriptor.id)

    def unregister(self, provider_id: str) -> None:
        with self._lock:
            self._providers.pop(provider_id, None)
            self._enabled.pop(provider_id, None)
            self._execution_bindings.pop(provider_id, None)
            self._reconciliation_repeatability_contracts.pop(provider_id, None)

    def enable(self, provider_id: str) -> ProviderDescriptor:
        with self._lock:
            self._require(provider_id)
            self._enabled[provider_id] = True
            return self._descriptor(provider_id)

    def disable(self, provider_id: str) -> ProviderDescriptor:
        with self._lock:
            self._require(provider_id)
            self._enabled[provider_id] = False
            return self._descriptor(provider_id)

    def reload(self, provider_id: str) -> ProviderDescriptor:
        with self._lock:
            self._require(provider_id)
            return self._descriptor(provider_id)

    def get(self, provider_id: str) -> CapabilityProvider:
        with self._lock:
            provider = self._providers[provider_id]
            _execution_lookup.set(_ExecutionLookup(self, provider_id, provider))
            return provider

    def capture_execution_target(
        self,
        provider_id: str,
        *,
        expected_provider: CapabilityProvider | None = None,
    ) -> tuple[CapabilityProvider, ProviderExecutionBinding]:
        """Atomically capture one live provider object and its exact binding.

        ``expected_provider`` closes the provider-lookup/binding-capture race at
        the RealityBoundary. If a same-id unregister/register occurred after
        the Boundary fetched the provider object, capture fails instead of
        pairing that old object with the replacement binding.
        """

        with self._lock:
            self._require(provider_id)
            provider = self._providers[provider_id]
            if expected_provider is not None and provider is not expected_provider:
                raise ValueError(
                    f"configured provider changed before dispatch: {provider_id}"
                )
            binding = self._execution_bindings[provider_id]
            current_digest = provider_execution_descriptor_digest(provider.descriptor)
            if binding.descriptor_digest != current_digest:
                raise ValueError(
                    f"configured provider descriptor drift for {provider_id!r}; re-register provider explicitly"
                )
            if binding.provider_id != provider_id:
                raise ValueError("provider execution binding/provider id mismatch")
            return provider, binding

    def capture_reconciliation_execution_target(
        self,
        provider_id: str,
        *,
        subject_identity: str,
        expected_provider: CapabilityProvider | None = None,
    ) -> tuple[
        CapabilityProvider,
        ProviderExecutionBinding,
        ReconciliationRepeatabilityAuthority | None,
    ]:
        """Coherently capture B and, when positive, exact-subject C authority.

        A missing, unknown, or non-repeat-safe configured contract produces no
        positive repeatability authority. The dispatch remains a valid B-bound
        historical execution fact, but automatic reconciliation repetition is
        ineligible until exact C authority exists.
        """

        with self._lock:
            provider, binding = self.capture_execution_target(
                provider_id,
                expected_provider=expected_provider,
            )
            contract = self._reconciliation_repeatability_contracts.get(provider_id)
            if contract is None or contract.repeatability_mode != "repeat-safe":
                return provider, binding, None
            if contract.provider_execution_binding_ref != binding.id:
                raise ValueError(
                    "configured reconciliation repeatability contract does not match execution binding"
                )
            authority = build_reconciliation_repeatability_authority(
                contract,
                subject_identity=subject_identity,
            )
            return provider, binding, authority

    def execution_binding(
        self,
        provider_id: str,
        *,
        expected_provider: CapabilityProvider | None = None,
    ) -> ProviderExecutionBinding:
        """Return the exact current binding; descriptor/object drift fails closed."""

        return self.capture_execution_target(
            provider_id,
            expected_provider=expected_provider,
        )[1]

    def reconciliation_repeatability_contract(
        self,
        provider_id: str,
        *,
        expected_provider: CapabilityProvider | None = None,
    ) -> ReconciliationRepeatabilityContract | None:
        """Return current configured C contract after exact B validation."""

        with self._lock:
            _, binding = self.capture_execution_target(
                provider_id,
                expected_provider=expected_provider,
            )
            contract = self._reconciliation_repeatability_contracts.get(provider_id)
            if contract is None:
                return None
            if contract.provider_execution_binding_ref != binding.id:
                raise ValueError(
                    "configured reconciliation repeatability contract drifted from execution binding"
                )
            return contract

    def resolve_execution_binding(
        self,
        historical: ProviderExecutionBinding,
    ) -> CapabilityProvider | None:
        """Resolve only an exact current configured identity; never retarget by provider id."""

        with self._lock:
            if historical.provider_id not in self._providers:
                return None
            try:
                provider, current = self.capture_execution_target(historical.provider_id)
            except (KeyError, ValueError):
                return None
            if current != historical:
                return None
            return provider

    def reconciliation_repeatability_eligibility(
        self,
        historical_authority: ReconciliationRepeatabilityAuthority | None,
        historical_binding: ProviderExecutionBinding | None,
        *,
        required_subject_identity: str,
    ) -> ReconciliationRepeatabilityEligibility:
        """Evaluate C against the current exact registry configuration, read-only."""

        with self._lock:
            if historical_binding is None:
                return evaluate_reconciliation_repeatability(
                    historical_authority,
                    historical_binding=None,
                    current_contract=None,
                    required_subject_identity=required_subject_identity,
                )
            current_provider = self.resolve_execution_binding(historical_binding)
            if current_provider is None:
                return ReconciliationRepeatabilityEligibility(
                    "ineligible",
                    False,
                    "exact historical configured-provider execution target is unavailable",
                )
            contract = self._reconciliation_repeatability_contracts.get(
                historical_binding.provider_id
            )
            return evaluate_reconciliation_repeatability(
                historical_authority,
                historical_binding=historical_binding,
                current_contract=contract,
                required_subject_identity=required_subject_identity,
            )

    def list_descriptors(self) -> builtins.list[ProviderDescriptor]:
        with self._lock:
            return [self._descriptor(provider_id) for provider_id in sorted(self._providers)]

    def list(self) -> builtins.list[ProviderDescriptor]:
        return self.list_descriptors()

    def providers_for(self, capability: str) -> builtins.list[ProviderDescriptor]:
        return [
            descriptor
            for descriptor in self.list_descriptors()
            if descriptor.enabled and capability in descriptor.capabilities
        ]

    def descriptors_for(self, capability: str, excluded: Iterable[str] = ()) -> builtins.list[ProviderDescriptor]:
        excluded_set = set(excluded)
        return [
            descriptor
            for descriptor in self.providers_for(capability)
            if descriptor.id not in excluded_set
        ]

    async def health(self, provider_id: str) -> ProviderHealth:
        with self._lock:
            provider = self._providers[provider_id]
            enabled = self._enabled.get(provider_id, False)
        try:
            result = await provider.health()
        except Exception as exc:  # provider failures must not crash the runtime
            return ProviderHealth(provider_id=provider_id, available=False, detail=str(exc))
        if not enabled:
            return result.model_copy(update={"available": False, "detail": "disabled"})
        return result

    def _descriptor(self, provider_id: str) -> ProviderDescriptor:
        descriptor = self._providers[provider_id].descriptor
        return descriptor.model_copy(update={"enabled": self._enabled.get(provider_id, False)})

    def _require(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise KeyError(f"unknown provider: {provider_id}")
