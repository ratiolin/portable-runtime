"""Raw executable transition artifact for the strict Level-6 REF-4 gate.

This module deliberately does *not* compute B0 observations.  It serializes the
canonical runtime records before and after one selected assertion transition.
The verified Lean side is responsible for reading the raw fields and computing
the restricted B0 projection.

The remaining trust boundary is therefore raw runtime serialization / I/O
fidelity, not Python-side semantic extraction of historical trace or current
qualification.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from portable_runtime.records.models import Assertion


class RawWithdrawalTransitionV1(BaseModel):
    """Versioned raw before/after envelope for one assertion transition.

    ``before_raw_snapshot`` and ``after_raw_snapshot`` are the direct
    ``Assertion.model_dump(mode="json")`` payloads.  They intentionally retain
    runtime-native field names such as ``record_type`` and ``epistemic_status``
    and contain no B0-derived fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["raw-withdrawal-transition-v1"] = "raw-withdrawal-transition-v1"
    subject_ref: str
    before_raw_snapshot: dict[str, Any]
    after_raw_snapshot: dict[str, Any]
    event_ref: str


def build_raw_withdrawal_transition(
    before: Assertion,
    after: Assertion,
    *,
    event_ref: str,
) -> RawWithdrawalTransitionV1:
    """Serialize one selected executable before/after transition without B0 interpretation.

    This function checks only envelope identity.  It does not require or infer
    ``supported -> revalidation-required`` and therefore cannot manufacture a
    successful B0 withdrawal certificate.  That judgment belongs to Lean.
    """

    if not event_ref:
        raise ValueError("event_ref must be non-empty")
    if before.id != after.id:
        raise ValueError("raw transition snapshots must refer to the same assertion id")

    return RawWithdrawalTransitionV1(
        subject_ref=before.id,
        before_raw_snapshot=before.model_dump(mode="json"),
        after_raw_snapshot=after.model_dump(mode="json"),
        event_ref=event_ref,
    )


__all__ = ["RawWithdrawalTransitionV1", "build_raw_withdrawal_transition"]
