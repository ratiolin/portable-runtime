"""Lease and fencing helpers used by the RealityBoundary orchestration.

This module is deliberately capability-free: it only reads a run snapshot and
compares request-owned lease facts.  It cannot resolve or invoke a provider.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from portable_runtime.core.capabilities import CapabilityRequest


def extract_lease_generation(request: CapabilityRequest) -> int | None:
    value = getattr(request, "lease_generation", None)
    if value is not None:
        return value
    if isinstance(request.metadata, dict):
        value = request.metadata.get("lease_generation")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def extract_lease_owner(request: CapabilityRequest) -> str | None:
    value = getattr(request, "lease_owner", None)
    if value is not None:
        return value
    if isinstance(request.metadata, dict):
        value = request.metadata.get("lease_owner")
        if isinstance(value, str):
            return value
    return None


def validate_fencing(
    request: CapabilityRequest,
    run: Any | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Validate request lease facts against one authoritative run snapshot."""

    if run is None or request.run_id is None:
        return True, "no run fencing required"
    current_time = now or datetime.now(UTC)
    if not run.lease_owner and (run.lease_generation == 0 or run.lease_generation is None):
        return True, "unleased run"
    request_generation = extract_lease_generation(request)
    request_owner = extract_lease_owner(request)
    if request_generation is None:
        return False, f"fencing: missing lease_generation, expected {run.lease_generation}"
    if request_generation != run.lease_generation:
        return False, f"fencing: generation mismatch request {request_generation} != current {run.lease_generation}"
    if run.lease_owner and request_owner is not None and request_owner != run.lease_owner:
        return False, f"fencing: owner mismatch {request_owner} != {run.lease_owner}"
    if run.lease_owner and request_owner is None:
        return False, f"fencing: missing lease_owner, expected {run.lease_owner}"
    if run.lease_expires_at is not None and run.lease_expires_at <= current_time:
        return False, f"fencing: lease expired at {run.lease_expires_at.isoformat()}"
    return True, "fencing ok"
