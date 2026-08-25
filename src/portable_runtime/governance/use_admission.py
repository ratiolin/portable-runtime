from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import sqlite3
from typing import Any, Literal

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.governance.canonical import (
    GOVERNANCE_HISTORY_EVENT_TYPES,
    reconstruct_governance_history,
)
from portable_runtime.governance.distinction import (
    GovernanceConfiguration,
    ReviewObligation,
    UseContext,
    blocking_review_open,
    obligation_blocks,
    scope_matches,
)

GovernanceUseAdmissionStatus = Literal[
    "not-applicable",
    "allowed",
    "blocked",
    "unavailable",
    "stale",
]

_GOVERNANCE_USE_REQUIREMENT_SCHEMA = "governance-use-requirement-v1"
_GOVERNANCE_USE_SNAPSHOT_SCHEMA = "governance-use-snapshot-v1"


def _digest_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def governance_not_applicable_digest() -> str:
    return _digest_payload(
        {
            "schema": _GOVERNANCE_USE_REQUIREMENT_SCHEMA,
            "applicable": False,
        }
    )


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
    requirement_digest: str | None = None
    snapshot_digest: str | None = None
    reason: str = ""

    @property
    def applicable(self) -> bool:
        return self.status != "not-applicable"


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
    def _requirement_digest(requirement: GovernanceUseRequirement) -> str:
        return _digest_payload(
            {
                "schema": _GOVERNANCE_USE_REQUIREMENT_SCHEMA,
                "applicable": True,
                "scheme_id": requirement.scheme_id,
                "use_context": {
                    "name": requirement.use_context.name,
                    "requested_scope": sorted(requirement.use_context.requested_scope),
                },
            }
        )

    @staticmethod
    def _blocking_predicate_payload(obligation: ReviewObligation) -> dict[str, Any]:
        condition = obligation.blocking_condition
        if condition is None:
            return {
                "mode": "context",
                "context": obligation.context,
            }
        return {
            "mode": "condition",
            "context_names": sorted(condition.context_names),
            "scope_any": sorted(condition.scope_any),
            "scope_all": sorted(condition.scope_all),
        }

    @classmethod
    def _snapshot_digest(
        cls,
        config: GovernanceConfiguration,
        requirement: GovernanceUseRequirement,
    ) -> str:
        """Digest only facts that can change this exact use-admission judgment."""

        state = config.states[requirement.scheme_id]
        relevant_blockers = [
            cls._blocking_predicate_payload(obligation)
            for obligation in config.runtime.obligations.values()
            if obligation.target == requirement.scheme_id
            and obligation_blocks(
                obligation,
                requirement.use_context,
                state.scope,
            )
        ]
        relevant_blockers.sort(
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
        )
        return _digest_payload(
            {
                "schema": _GOVERNANCE_USE_SNAPSHOT_SCHEMA,
                "scheme_id": requirement.scheme_id,
                "use_context": {
                    "name": requirement.use_context.name,
                    "requested_scope": sorted(requirement.use_context.requested_scope),
                },
                "projection": {
                    "qualification": state.qualification,
                    "activation": state.activation,
                    "scope": sorted(state.scope),
                },
                "relevant_blockers": relevant_blockers,
            }
        )

    def evaluate(
        self,
        request: CapabilityRequest,
        resolver: GovernanceUseRequirementResolver | None,
    ) -> GovernanceUseAdmissionDecision:
        not_applicable_digest = governance_not_applicable_digest()
        if resolver is None:
            return GovernanceUseAdmissionDecision(
                status="not-applicable",
                requirement_digest=not_applicable_digest,
                snapshot_digest=not_applicable_digest,
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
                requirement_digest=not_applicable_digest,
                snapshot_digest=not_applicable_digest,
                reason="capability use is not governance-bound",
            )

        requirement_digest = self._requirement_digest(requirement)
        if not requirement.scheme_id:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                reason="governance-use requirement has no scheme identity",
            )

        try:
            before = self._canonical_events()
        except Exception as exc:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                reason=f"canonical governance history unavailable: {exc}",
            )

        if not before:
            legacy = self._legacy_sidecar_present()
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
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
                requirement_digest=requirement_digest,
                reason=f"canonical governance history is not usable: {exc}",
            )

        try:
            after = self._canonical_events()
        except Exception as exc:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                reason=f"canonical governance history recheck failed: {exc}",
            )
        if self._event_fingerprint(after) != before_digest:
            return GovernanceUseAdmissionDecision(
                status="stale",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                reason="canonical governance history changed during admission",
            )

        config = history.configuration
        state = config.states.get(requirement.scheme_id)
        if state is None:
            return GovernanceUseAdmissionDecision(
                status="unavailable",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                reason="canonical governance history has no required distinction projection",
            )

        digest = self._snapshot_digest(config, requirement)
        if state.qualification != "qualified":
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                snapshot_digest=digest,
                reason=f"distinction qualification is {state.qualification!r}",
            )
        if state.activation != "active":
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
                snapshot_digest=digest,
                reason=f"distinction activation is {state.activation!r}",
            )
        if not scope_matches(state.scope, requirement.use_context):
            return GovernanceUseAdmissionDecision(
                status="blocked",
                scheme_id=requirement.scheme_id,
                use_context=requirement.use_context,
                requirement_digest=requirement_digest,
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
                requirement_digest=requirement_digest,
                snapshot_digest=digest,
                reason="blocking governance review is open for this use context",
            )
        return GovernanceUseAdmissionDecision(
            status="allowed",
            scheme_id=requirement.scheme_id,
            use_context=requirement.use_context,
            requirement_digest=requirement_digest,
            snapshot_digest=digest,
            reason="canonical governance snapshot permits this use",
        )