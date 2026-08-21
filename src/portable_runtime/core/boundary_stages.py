"""Private stage seam for :class:`RealityBoundary`.

The public interface remains ``RealityBoundary.execute``.  These small value
objects keep stage inputs and provider-facing execution facts explicit without
granting any stage a provider capability.  In particular, no stage in this
module may call a provider; the only reality exit remains the invocation block
in ``core/boundary.py``.
"""

from __future__ import annotations

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
