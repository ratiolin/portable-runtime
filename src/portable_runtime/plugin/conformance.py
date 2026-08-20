from __future__ import annotations

from uuid import uuid4

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
from portable_runtime.interfaces.provider import CapabilityProvider


async def check_provider(provider: CapabilityProvider) -> list[str]:
    """Run the small provider contract suite without touching Runtime state."""

    errors: list[str] = []
    descriptor = provider.descriptor
    if not descriptor.id or not descriptor.version:
        errors.append("descriptor id/version are required")
    if not descriptor.capabilities:
        errors.append("descriptor must declare capabilities")
    health = await provider.health()
    if not health.available:
        errors.append(f"health unavailable: {health.detail}")
        return errors
    for capability in descriptor.capabilities:
        request = CapabilityRequest(
            id=f"conformance_{uuid4().hex}",
            capability=capability,
            instruction="provider conformance probe",
        )
        try:
            result = await provider.invoke(request, InvocationContext(runtime_id="conformance"))
        except Exception as exc:  # noqa: BLE001 - provider boundary
            errors.append(f"invoke raised: {exc}")
            continue
        if result.request_id != request.id:
            errors.append("result request_id does not match")
        if result.provider_id != descriptor.id:
            errors.append("result provider_id does not match descriptor")
        if result.status not in {"succeeded", "failed", "unavailable", "needs-input", "cancelled"}:
            errors.append("result status is invalid")
        if result.status == "failed" and result.error:
            errors.append(f"invoke failed: {result.error}")
    try:
        await provider.cancel("conformance-missing-request")
    except Exception as exc:  # noqa: BLE001 - provider boundary
        errors.append(f"cancel raised: {exc}")
    return errors
