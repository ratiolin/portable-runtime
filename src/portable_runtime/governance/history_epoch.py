from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from portable_runtime.governance.canonical import (
    GOVERNANCE_HISTORY_EVENT_TYPES,
    validate_governance_history_event,
)

if TYPE_CHECKING:
    from portable_runtime.governance.persistence import DistinctionGovernancePersistence

GovernanceHistoryEpoch = Literal[
    "EMPTY",
    "CANONICAL",
    "LEGACY_PROVABLE",
    "LEGACY_INCOMPLETE",
]


@dataclass(frozen=True)
class GovernanceHistoryEpochStatus:
    epoch: GovernanceHistoryEpoch
    canonical_event_count: int
    sidecar_record_count: int
    reason: str


def _sidecar_count(persistence: DistinctionGovernancePersistence) -> int:
    return (
        len(persistence.list_states())
        + len(persistence.list_obligations())
        + len(persistence.list_decisions())
        + len(persistence.list_applications())
    )


def _legacy_current_configuration_is_provable(
    persistence: DistinctionGovernancePersistence,
) -> tuple[bool, str]:
    obligations = persistence.list_obligations()
    decisions = persistence.list_decisions()
    applications = persistence.list_applications()

    if any(not obligation.trigger_ref for obligation in obligations.values()):
        return False, "open legacy review obligation is missing its EventInstance provenance"

    open_review_refs = set(obligations)
    for decision in decisions.values():
        missing = set(decision.review_refs).difference(open_review_refs)
        if missing:
            return False, "legacy decision references review responsibility no longer represented in sidecar"

    for receipt in applications.values():
        application = receipt.application
        if receipt.effect_kind == "review_discharge" or application.review_obligation_id is not None:
            return False, "legacy discharged review lost the original EventInstance provenance"
        if application.decision_ref not in decisions:
            return False, "legacy application references a missing governance decision"

    return True, "current legacy governance configuration has deterministic surviving provenance"


def detect_governance_history_epoch(
    persistence: DistinctionGovernancePersistence,
) -> GovernanceHistoryEpochStatus:
    """Classify governance history without inventing missing provenance.

    ``LEGACY_PROVABLE`` means the current configuration can be deterministically
    canonicalized from surviving sidecar provenance. It does not claim that the
    original pre-D.5 temporal event sequence can be reconstructed.
    """

    events = [
        event
        for event in persistence.store.list_events()
        if getattr(event, "type", "") in GOVERNANCE_HISTORY_EVENT_TYPES
    ]
    sidecar_count = _sidecar_count(persistence)

    if events:
        for event in events:
            validate_governance_history_event(event)
        return GovernanceHistoryEpochStatus(
            epoch="CANONICAL",
            canonical_event_count=len(events),
            sidecar_record_count=sidecar_count,
            reason="supported canonical governance history is present",
        )

    if sidecar_count == 0:
        return GovernanceHistoryEpochStatus(
            epoch="EMPTY",
            canonical_event_count=0,
            sidecar_record_count=0,
            reason="no governance sidecar and no canonical governance history",
        )

    provable, reason = _legacy_current_configuration_is_provable(persistence)
    return GovernanceHistoryEpochStatus(
        epoch="LEGACY_PROVABLE" if provable else "LEGACY_INCOMPLETE",
        canonical_event_count=0,
        sidecar_record_count=sidecar_count,
        reason=reason,
    )
