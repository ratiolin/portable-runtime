from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.governance.canonical import (
    GOVERNANCE_HISTORY_EVENT_TYPES,
    obligation_payload,
    reconstruct_governance_history,
    state_payload,
)
from portable_runtime.governance.distinction import (
    GovernanceConfiguration,
    UseContext,
    blocking_review_open,
    scope_matches,
)

GovernanceUseAdmissionStatus = Literal[
    "not-applicable",
    "allowed",
    "blocked",
    "unavailable",
    "stale",
]


@dataclass(frozen=True)
class GovernanceUseRequirement:
    """Runtime-owned requirement that one capability use is governance-bound.

    The requirement must come from runtime configuration/contract ownership.
    It is intentionally independent from the governance sidecar and from
    caller-controlled request metadata.
    """

    scheme_id: str
    use_context: UseContext


GovernanceUseRequirementResolver = Callable[
    [CapabilityRequest], GovernanceUseRequirement | None
]


@dataclass(frozen=True)
class GovernanceUseAdmissionDecision:
    status: GovernanceUseAdmissionStatus
    scheme_id: str | None = None
    use_context: UseContext | None = None
    snapshot_digest: str | None = None
    reason: str = ""


class GovernanceUseAdmission:
    """Read-only admission from canonical distinction-governance history.

    Canonical events are authoritative. The private governance sidecar is
    never consulted to decide usability and is never hydrated by this class.
    Legacy sidecar state is only detected so governed use can fail closed and
    require an explicit migration outside the invocation path.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def _event_fingerprint(events: list[Any]) -> str:
        rows: list[dict[str, Any]] = []
        for event in events:
            payload = getattr(event, "payload", {})
            rows.append(
                {
                    "id": str(getattr(event, "id", "")),
                    "type": str(getattr(event, "type", "")),
                    "subject_ref": str(getattr(event, "subject_ref", "")),
                    "payload": payload if isinstance(payload, dict) else {},
                }
            )
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _canonical_events(self) -> list[Any]:
        if self.store is None or not hasattr(self.store, "list_events"):
            raise RuntimeError("canonical event journal unavailable")
        return [
            event
            for event in self.store.list_events()
            if getattr(event, "type", "") in GOVERNANCE_HISTORY_EVENT_TYPES
        ]

    def _legacy_sidecar_present(self) -> bool:
        """Detect pre-D.5 sidecar presence without making it admission truth."""

        namespace = vars(self.store)
        records = namespace.get("_distinction_governance_records")
        if isinstance(records, dict):
            return any(bool(values) for values in records.values())

        connection = namespace.get("_connection")
        if isinstance(connection, sqlite3.Connection):
            try:
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='runtime_governance_records'"
                ).fetchone()
                if table is None:
                    return False
                row = connection.execute(
                    "SELECT COUNT(*) AS n FROM runtime_governance_records"
                ).fetchone()
                if row is None:
                    return False
                try:
                    return int(row["n"]) > 0
                except (IndexError, KeyError, TypeError):
                    return int(row[0]) > 0
            except sqlite3.Error:
                # Failure to inspect a possible legacy governance projection is
                # not evidence that the runtime is ungoverned.
                return True
        return False

    @staticmethod
    def _snapshot_digest(
        config: GovernanceConfiguration,
        requirement: GovernanceUseRequirement,
    ) -> str:
        state = config.states[requirement.scheme_id]
        obligations = [
            obligation_payload(obligation)
            for obligation in config.runtime.obligations.values()
            if obligation.target == requirement.scheme_id
        ]
        obligations.sort(key=lambda item: str(item.get("id", "")))
        payload = {
            "scheme_id": requirement.scheme_id,
            "use_context": {
                "name": requirement.use_context.name,
                "requested_scope": sorted(requirement.use_context.requested_scope),
            },
            "state": state_payload(requirement.scheme_id, state),
            "open_obligations": obligations,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def evaluate(
        self,
        request: CapabilityRequest,
        resolver: GovernanceUseRequirementResolver | None,
    ) -> GovernanceUseAdmissionDecision:
        if resolver is None:
            return GovernanceUseAdmissionDecision(
                status="not-applicable",
                reason="no runtime governance-use requirement",
            )
        try:
            requirement = resolver(request)
        except Exception as exc:  # runtime-owned requirement state is fail-closed
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                reason=f"governance-use requirement resolution failed: {exc}",
            )
        if requirement is None:
            return GovernanceUseAdmissionDecision(
                status="not-applicable",
                reason="capability use is not governance-bound",
            )
        if not requirement.scheme_id:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                use_context=requirement.use_context,
                reason="governance-use requirement has no scheme identity",
            )

        try:
            before = self._canonical_events()
        except Exception as exc:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason=f"canonical governance history unavailable: {exc}",
            )

        if not before:
            legacy = self._legacy_sidecar_present()
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason=(
                    "legacy governance projection requires explicit migration"
                    if legacy
                    else "governed use requires canonical governance history"
                ),
            )

        before_digest = self._event_fingerprint(before)
        try:
            history = reconstruct_governance_history(before)
        except Exception as exc:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason=f"canonical governance history is not usable: {exc}",
            )

        try:
            after = self._canonical_events()
        except Exception as exc:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason=f"canonical governance history recheck failed: {exc}",
            )
        if self._event_fingerprint(after) != before_digest:
            return GovernanceUseAdmissionDecision(
                status="stale",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason="canonical governance history changed during admission",
            )

        config = history.configuration
        state = config.states.get(requirement.scheme_id)
        if state is None:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                reason="canonical governance history has no required distinction projection",
            )

        digest = self._snapshot_digest(config, requirement)
        if state.qualification != "qualified":
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                snapshot_digest=digest,
                reason=f"distinction qualification is {state.qualification!r}",
            )
        if state.activation != "active":
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                snapshot_digest=digest,
                reason=f"distinction activation is {state.activation!r}",
            )
        if not scope_matches(state.scope, requirement.use_context):
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                snapshot_digest=digest,
                reason="requested use scope is outside the governed distinction scope",
            )
        if blocking_review_open(
            config,
            requirement.scheme_id,
            requirement.use_context,
        ):
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                snapshot_digest=digest,
                reason="blocking governance review is open for this use context",
            )
        return GovernanceUseAdmissionDecision(
            status="allowed",
            scheme_id=requirement.scheme_id,
            use_context=requirement.use_context,
            snapshot_digest=digest,
            reason="canonical governance snapshot permits this use",
        )
