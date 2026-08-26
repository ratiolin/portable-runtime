"""Exact-target reconciliation reality exit.

This boundary owns exactly one provider ``reconcile`` call against a provider
object that has already been resolved from authoritative historical execution
binding.  It deliberately has no registry dependency and performs no recovery
policy, repeatability, retry, or application-completion decisions.
"""

from __future__ import annotations

from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.interfaces.provider import CapabilityProvider


class RecoveryReconciliationRealityBoundary:
    """Narrow reality boundary for one exact reconciliation target."""

    async def reconcile_exact_target(
        self,
        *,
        provider: CapabilityProvider,
        request_id: str,
    ) -> CapabilityResult | None:
        """Query one already-resolved provider target without registry lookup."""

        reconcile = getattr(provider, "reconcile", None)
        if not callable(reconcile):
            return None
        provider_id = provider.descriptor.id
        try:
            return await reconcile(request_id)
        except Exception as exc:  # noqa: BLE001 - external reality failure is data
            return CapabilityResult(
                request_id=request_id,
                provider_id=provider_id,
                status="unknown",
                message=f"reconciliation failed: {exc}",
                error={"code": "ReconciliationUnavailable", "reason": str(exc)},
            )
