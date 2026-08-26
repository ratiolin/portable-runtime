"""Authoritative reconciliation consumer for one RecoveryApplication.

The consumer owns only the A/B/C orchestration chain:

RecoveryApplication -> A-first completion check -> exact B resolution -> exact C
eligibility -> exact-target reconciliation reality exit -> store-owned A commit.

It creates no fresh CapabilityRequest, InvocationPermit, StepAttempt, dispatch,
Outcome, RecoveryDisposition, RecoveryApplication, reconciliation-attempt fact,
or generic RecoveryApplicationConsumed fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.core.reconciliation_boundary import (
    RecoveryReconciliationRealityBoundary,
)
from portable_runtime.core.reconciliation_repeatability import (
    reconciliation_repeatability_authority_from_dispatch,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.provider_execution_binding import (
    provider_execution_binding_from_dispatch,
)
from portable_runtime.workflows.recovery_application import (
    RecoveryApplication,
    RecoveryApplicationCommitRequest,
    prepare_recovery_application_commit,
    recovery_application_from_event,
)
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
)
from portable_runtime.workflows.recovery_observation import (
    RecoveryReportedStatus,
    reported_status_from_capability_status,
)

RecoveryReconciliationStatus = Literal[
    "replayed",
    "completed",
    "unavailable",
    "unknown",
    "conflicted",
]


@dataclass(frozen=True)
class RecoveryReconciliationRequest:
    """Caller supplies only one opaque durable RecoveryApplication identity."""

    recovery_application_ref: str


@dataclass(frozen=True)
class RecoveryReconciliationResult:
    """Non-durable orchestration result for one consumer invocation."""

    status: RecoveryReconciliationStatus
    recovery_application_ref: str
    recovery_observation_ref: str | None = None
    provider_result: CapabilityResult | None = None
    reason: str = ""

    @property
    def replayed(self) -> bool:
        return self.status == "replayed"

    @property
    def durable_completion(self) -> bool:
        return (
            self.status in {"completed", "replayed"}
            and self.recovery_observation_ref is not None
        )


class RecoveryReconciliationConsumer:
    """Consume one exact reconciliation-request RecoveryApplication."""

    def __init__(
        self,
        *,
        store: Any,
        registry: ProviderRegistry,
        reality_boundary: RecoveryReconciliationRealityBoundary | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.reality_boundary = reality_boundary or RecoveryReconciliationRealityBoundary()

    def _result(
        self,
        status: RecoveryReconciliationStatus,
        application_ref: str,
        *,
        observation_ref: str | None = None,
        provider_result: CapabilityResult | None = None,
        reason: str = "",
    ) -> RecoveryReconciliationResult:
        return RecoveryReconciliationResult(
            status=status,
            recovery_application_ref=application_ref,
            recovery_observation_ref=observation_ref,
            provider_result=provider_result,
            reason=reason,
        )

    def _exact_application(self, application_ref: str) -> RecoveryApplication:
        event = self.store.get_event(application_ref)
        if event is None or event.id != application_ref:
            raise LookupError("exact durable RecoveryApplication is unavailable")
        application = recovery_application_from_event(event)
        replay = prepare_recovery_application_commit(
            self.store,
            RecoveryApplicationCommitRequest(
                disposition_ref=application.disposition_ref,
            ),
        )
        if not replay.replayed or replay.application.id != application_ref:
            raise ValueError("RecoveryApplication durable identity rebound")
        if replay.application != application:
            raise ValueError("RecoveryApplication source graph or semantics rebound")
        return application

    async def consume(
        self,
        request: RecoveryReconciliationRequest,
    ) -> RecoveryReconciliationResult:
        application_ref = request.recovery_application_ref.strip()
        if not application_ref:
            return self._result(
                "unavailable",
                request.recovery_application_ref,
                reason="reconciliation consumer requires exact RecoveryApplication ref",
            )

        get_completion = getattr(
            self.store,
            "get_recovery_application_observation",
            None,
        )
        commit_completion = getattr(
            self.store,
            "commit_recovery_application_observation",
            None,
        )
        if not callable(get_completion) or not callable(commit_completion):
            return self._result(
                "unavailable",
                application_ref,
                reason=(
                    "StateStore lacks exact application-bound RecoveryObservation authority"
                ),
            )

        # Validate the complete durable application authority graph before any
        # current-state dependency or reality exit.
        try:
            application = self._exact_application(application_ref)
        except LookupError as exc:
            return self._result("unavailable", application_ref, reason=str(exc))
        except (TypeError, ValueError) as exc:
            return self._result("conflicted", application_ref, reason=str(exc))

        if application.application_kind != "reconciliation-request":
            return self._result(
                "unavailable",
                application_ref,
                reason="RecoveryApplication is not a reconciliation-request responsibility",
            )

        # A-first is semantic. Once durable completion exists, no current
        # provider configuration or repeatability state may reopen responsibility.
        try:
            existing = get_completion(application.id)
        except Exception as exc:  # noqa: BLE001 - malformed durable A fails closed
            return self._result("conflicted", application_ref, reason=str(exc))
        if existing is not None:
            if existing.recovery_application_ref != application.id:
                return self._result(
                    "conflicted",
                    application_ref,
                    reason="application-bound RecoveryObservation rebound",
                )
            return self._result(
                "replayed",
                application_ref,
                observation_ref=existing.id,
                reason="application reconciliation responsibility already durably completed",
            )

        # Re-read the exact historical dispatch only after A has proven absent.
        dispatch = self.store.get_event(application.source_dispatch_ref)
        if dispatch is None or dispatch.id != application.source_dispatch_ref:
            return self._result(
                "conflicted",
                application_ref,
                reason="exact historical InvocationDispatchCommitted is unavailable",
            )

        # B: decode the original configured-provider execution identity and
        # resolve only the exact current configured identity. Same provider id
        # is never sufficient.
        try:
            historical_binding = provider_execution_binding_from_dispatch(dispatch)
        except (TypeError, ValueError) as exc:
            return self._result("unavailable", application_ref, reason=str(exc))
        try:
            provider = self.registry.resolve_execution_binding(historical_binding)
        except Exception as exc:  # noqa: BLE001 - registry failure is unavailable
            return self._result("unavailable", application_ref, reason=str(exc))
        if provider is None:
            return self._result(
                "unavailable",
                application_ref,
                reason="exact historical configured-provider execution target is unavailable",
            )
        if provider.descriptor.id != application.source_provider_id:
            return self._result(
                "conflicted",
                application_ref,
                reason="resolved provider target does not match RecoveryApplication source graph",
            )

        # C: positive historical exact-subject authority must still match the
        # exact current B-bound reconciliation protocol/contract.
        try:
            historical_repeatability = reconciliation_repeatability_authority_from_dispatch(
                dispatch
            )
        except (TypeError, ValueError) as exc:
            return self._result("unavailable", application_ref, reason=str(exc))
        try:
            eligibility = self.registry.reconciliation_repeatability_eligibility(
                historical_repeatability,
                historical_binding,
                required_subject_identity=application.source_request_ref,
            )
        except Exception as exc:  # noqa: BLE001 - registry/config drift fails closed
            return self._result("unavailable", application_ref, reason=str(exc))
        if not eligibility.eligible:
            return self._result(
                "unavailable",
                application_ref,
                reason=eligibility.reason or "reconciliation repeatability is ineligible",
            )

        # Sole reality exit. The exact provider object is passed through and is
        # never converted back into a provider-id lookup.
        provider_result = await self.reality_boundary.reconcile_exact_target(
            provider=provider,
            request_id=application.source_request_ref,
        )
        reported_status: RecoveryReportedStatus
        if provider_result is not None:
            if provider_result.request_id != application.source_request_ref:
                return self._result(
                    "conflicted",
                    application_ref,
                    provider_result=provider_result,
                    reason="provider reconciliation result request identity mismatch",
                )
            if provider_result.provider_id != application.source_provider_id:
                return self._result(
                    "conflicted",
                    application_ref,
                    provider_result=provider_result,
                    reason="provider reconciliation result target identity mismatch",
                )
            reported_status = reported_status_from_capability_status(provider_result.status)
        else:
            reported_status = "reported-unknown"

        # A is the durable completion linearization point. No generic P1
        # observation fallback is allowed. Stable B/C authority refs are the
        # only provenance used here; transient response identity is not allowed
        # to redefine application completion identity.
        try:
            observation = commit_completion(
                RecoveryApplicationObservationCommitRequest(
                    recovery_application_ref=application.id,
                    observation_source="provider-reconcile-exact-target",
                    reported_status=reported_status,
                    provenance_refs=(
                        historical_binding.id,
                        historical_repeatability.id,
                    ),
                )
            )
        except ValueError as exc:
            # A store owns rebound detection. A conflicting overlapping result
            # cannot become a second completion observation or latest-wins state.
            return self._result(
                "conflicted",
                application_ref,
                provider_result=provider_result,
                reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - post-reality persistence failure
            return self._result(
                "unknown",
                application_ref,
                provider_result=provider_result,
                reason=f"reconciliation result could not be durably completed: {exc}",
            )

        if observation.recovery_application_ref != application.id:
            return self._result(
                "conflicted",
                application_ref,
                provider_result=provider_result,
                reason="application-bound RecoveryObservation commit rebound",
            )
        return self._result(
            "completed",
            application_ref,
            observation_ref=observation.id,
            provider_result=provider_result,
            reason="reconciliation responsibility durably completed",
        )
