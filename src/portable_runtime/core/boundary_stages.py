"""Private stage seam for :class:`RealityBoundary`.

The public interface remains ``RealityBoundary.execute``.  These small value
objects keep stage inputs and provider-facing execution facts explicit without
granting any stage a provider capability.  In particular, no stage in this
module may call a provider; the only reality exit remains the invocation block
in ``core/boundary.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ReliabilityStageInput:
    """Normalized governance input passed from Boundary to reliability."""

    side_effect: bool
    action_blast_radius: int
    exposure: int | None
    irreversible: bool
    procedure_profile: str
    timing: dict[str, Any] | None

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "side_effect": self.side_effect,
            "action_blast_radius": self.action_blast_radius,
            "exposure": self.exposure,
            "irreversible": self.irreversible,
            "procedure_profile": self.procedure_profile,
            "timing": self.timing,
        }


@dataclass(frozen=True)
class InvocationStagePlan:
    """Provider facts consumed by Boundary's sole invocation stage."""

    provider_id: str
    side_effect_class: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
    effect_semantics: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"]

    @classmethod
    def from_descriptor(cls, descriptor: Any) -> InvocationStagePlan:
        side_effect_class = str(getattr(descriptor, "side_effect_class", "pure"))
        allowed = {"pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"}
        if side_effect_class not in allowed:
            side_effect_class = "irreversible-opaque"
        effect_semantics = str(getattr(descriptor, "effect_semantics", side_effect_class))
        if effect_semantics not in allowed:
            effect_semantics = side_effect_class
        reversibility = str(getattr(descriptor, "reversibility", "unknown"))
        if reversibility not in {"reversible", "compensatable", "irreversible", "unknown"}:
            reversibility = "unknown"
        return cls(
            provider_id=str(getattr(descriptor, "id", "")),
            side_effect_class=side_effect_class,  # type: ignore[arg-type]
            effect_semantics=effect_semantics,  # type: ignore[arg-type]
            reversibility=reversibility,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class BoundaryStagePlan:
    """The internal stage order; callers only see ``RealityBoundary.execute``."""

    names: tuple[str, ...] = (
        "qualification",
        "policy",
        "authorization",
        "procedure",
        "reliability",
        "routing",
        "precommit",
        "invocation",
        "postcondition",
        "projection",
    )
    provider_invocation_owner: str = "RealityBoundary"


@dataclass(frozen=True)
class ReliabilityStageDecision:
    """Result of the private reliability stage implementation."""

    allowed: bool
    reason: str | None = None
    error: Exception | None = None


def evaluate_reliability_stage(
    reliability: Any,
    stage_input: ReliabilityStageInput,
    call_supported: Callable[..., Any],
) -> ReliabilityStageDecision:
    """Evaluate reliability without exposing a provider capability."""

    try:
        if hasattr(reliability, "assess"):
            allowed, reason = call_supported(reliability.assess, **stage_input.as_kwargs())
        else:
            allowed = call_supported(reliability.can_execute, **stage_input.as_kwargs())
            reason = getattr(reliability, "last_block_reason", None) or "reliability budget exhausted"
        return ReliabilityStageDecision(bool(allowed), str(reason) if reason is not None else None)
    except Exception as exc:  # pragma: no cover - caller maps the typed failure
        return ReliabilityStageDecision(False, error=exc)


@dataclass(frozen=True)
class ProviderSelectionDecision:
    """Provider health/routing result; invocation remains owned by Boundary."""

    healthy: tuple[Any, ...]
    selected: Any | None = None
    error: Exception | None = None
    error_phase: Literal["eligibility", "routing"] | None = None


async def select_provider_stage(
    registry: Any,
    routing: Any,
    request: Any,
    descriptors: Sequence[Any],
    circuit_for: Callable[[str], Any],
) -> ProviderSelectionDecision:
    """Run health, circuit and constraint selection before the reality exit."""

    healthy: list[Any] = []
    for descriptor in descriptors:
        try:
            health = await registry.health(descriptor.id)
            if not health.available:
                continue
            if not circuit_for(descriptor.id).allow():
                continue
            healthy.append(descriptor)
        except Exception as exc:  # pragma: no cover - caller maps the typed failure
            return ProviderSelectionDecision(tuple(healthy), error=exc, error_phase="eligibility")
    try:
        selected = await routing.select(request, healthy) if healthy else None
    except Exception as exc:  # pragma: no cover - caller maps the typed failure
        return ProviderSelectionDecision(tuple(healthy), error=exc, error_phase="routing")
    return ProviderSelectionDecision(tuple(healthy), selected=selected)
