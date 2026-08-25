from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal, cast

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Event
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirementResolver,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

DISPATCH_COMMIT_EVENT = "InvocationDispatchCommitted"
DISPATCH_COMMIT_SCHEMA = "governance-dispatch-commit-v1"

DispatchCommitStatus = Literal[
    "not-applicable",
    "committed",
    "blocked",
    "changed",
    "unavailable",
    "stale",
]
DispatchRecoveryMode = Literal[
    "uncommitted",
    "idempotent-retry",
    "reconcile",
    "unknown",
]


@dataclass(frozen=True)
class DispatchCommitDecision:
    status: DispatchCommitStatus
    commit_ref: str | None = None
    reason: str = ""
    current_snapshot_digest: str | None = None


class DispatchLinearizationError(RuntimeError):
    """The authoritative StateStore cannot provide a linearized write scope."""


@contextmanager
def _dispatch_linearized_write(store: Any) -> Iterator[None]:
    """Serialize governance truth and dispatch commitment in one store domain.

    The supported portable-local domains are one in-memory StateStore object
    and one SQLite database. SQLite deliberately uses ``BEGIN IMMEDIATE`` so
    the dispatch claim competes with canonical governance mutations for the
    same writer serialization point before reading governance truth.
    """

    if isinstance(store, InMemoryStateStore):
        with store.transaction():
            yield
        return

    if isinstance(store, SQLiteStateStore):
        namespace = vars(store)
        connection = cast(sqlite3.Connection, namespace["_connection"])
        lock = namespace["_lock"]
        with lock:
            if connection.in_transaction:
                raise DispatchLinearizationError(
                    "dispatch commitment requires a top-level SQLite write transaction"
                )
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return

    raise DispatchLinearizationError(
        "StateStore does not support governance dispatch linearization"
    )


def _dispatch_commit_ref(
    request: CapabilityRequest,
    permit: InvocationPermit,
    attempt_id: str | None,
) -> str:
    payload = {
        "schema": DISPATCH_COMMIT_SCHEMA,
        "request_id": request.id,
        "provider_id": permit.provider_id,
        "attempt_id": attempt_id,
        "invocation_permit_digest": permit.request_digest,
        "governance_requirement_digest": permit.governance_requirement_digest,
        "governance_snapshot_digest": permit.governance_snapshot_digest,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"dispatch_{hashlib.sha256(raw.encode()).hexdigest()}"


def dispatch_recovery_mode(step: Any, attempt: Any) -> DispatchRecoveryMode:
    """Classify recovery after a durable dispatch commitment.

    A committed attempt is never equivalent to a fresh, never-dispatched
    invocation. Idempotent/deduplicatable work may be retried only under the
    same idempotency identity; reconcilable work must reconcile; opaque work is
    unknown and requires explicit recovery.
    """

    metadata = getattr(attempt, "metadata", {})
    if not isinstance(metadata, dict) or not metadata.get("dispatch_commit_ref"):
        return "uncommitted"
    semantics = str(getattr(step, "effect_semantics", ""))
    if semantics in {"idempotent", "deduplicatable"}:
        return "idempotent-retry"
    if semantics == "reconcilable":
        return "reconcile"
    return "unknown"


class GovernanceDispatchCommitter:
    """Linearize one governed dispatch claim against canonical governance.

    This bridge never owns provider capability. It only establishes a durable
    execution fact after validating the exact governance judgment bound into
    ``InvocationPermit`` while holding the authoritative StateStore write
    serialization domain.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def commit(
        self,
        request: CapabilityRequest,
        permit: InvocationPermit,
        resolver: GovernanceUseRequirementResolver | None,
        *,
        attempt_id: str | None,
    ) -> DispatchCommitDecision:
        if not permit.governance_applicable:
            return DispatchCommitDecision(
                status="not-applicable",
                reason="invocation permit is explicitly not governance-bound",
            )
        if self.store is None:
            return DispatchCommitDecision(
                status="unavailable",
                reason="governed dispatch requires an authoritative StateStore",
            )

        try:
            with _dispatch_linearized_write(self.store):
                current = GovernanceUseAdmission(self.store).evaluate(request, resolver)
                if current.status == "unavailable":
                    return DispatchCommitDecision(
                        status="unavailable",
                        reason=current.reason,
                        current_snapshot_digest=current.snapshot_digest,
                    )
                if current.status == "stale":
                    return DispatchCommitDecision(
                        status="stale",
                        reason=current.reason,
                        current_snapshot_digest=current.snapshot_digest,
                    )
                if current.status == "blocked":
                    return DispatchCommitDecision(
                        status="blocked",
                        reason=current.reason,
                        current_snapshot_digest=current.snapshot_digest,
                    )
                if current.status != "allowed":
                    return DispatchCommitDecision(
                        status="changed",
                        reason="governed dispatch no longer has an applicable allowed judgment",
                        current_snapshot_digest=current.snapshot_digest,
                    )
                if (
                    current.requirement_digest != permit.governance_requirement_digest
                    or current.snapshot_digest != permit.governance_snapshot_digest
                ):
                    return DispatchCommitDecision(
                        status="changed",
                        reason="dispatch governance judgment does not match InvocationPermit",
                        current_snapshot_digest=current.snapshot_digest,
                    )

                commit_ref = _dispatch_commit_ref(request, permit, attempt_id)
                event = Event(
                    id=commit_ref,
                    type=DISPATCH_COMMIT_EVENT,
                    subject_ref=request.id,
                    payload={
                        "schema": DISPATCH_COMMIT_SCHEMA,
                        "request_id": request.id,
                        "provider_id": permit.provider_id,
                        "attempt_ref": attempt_id,
                        "invocation_permit_digest": permit.request_digest,
                        "qualification_digest": permit.qualification_digest,
                        "governance_requirement_digest": permit.governance_requirement_digest,
                        "governance_snapshot_digest": permit.governance_snapshot_digest,
                        "lease_generation": permit.lease_generation,
                        "linearization_domain": "authoritative-state-store",
                    },
                )

                if attempt_id is not None:
                    if not hasattr(self.store, "get_attempt") or not hasattr(
                        self.store, "save_attempt"
                    ):
                        raise DispatchLinearizationError(
                            "dispatch attempt binding is unavailable"
                        )
                    attempt = self.store.get_attempt(attempt_id)
                    if attempt is None:
                        raise DispatchLinearizationError(
                            "dispatch commitment references a missing StepAttempt"
                        )
                    metadata = dict(getattr(attempt, "metadata", {}) or {})
                    existing_ref = metadata.get("dispatch_commit_ref")
                    if existing_ref not in {None, commit_ref}:
                        raise DispatchLinearizationError(
                            "StepAttempt dispatch commitment cannot be rebound"
                        )
                    metadata.update(
                        {
                            "dispatch_commit_ref": commit_ref,
                            "governance_requirement_digest": permit.governance_requirement_digest,
                            "governance_snapshot_digest": permit.governance_snapshot_digest,
                            "invocation_permit_digest": permit.request_digest,
                        }
                    )
                    self.store.save_attempt(
                        attempt.model_copy(update={"metadata": metadata})
                    )

                self.store.append_event(event)
                return DispatchCommitDecision(
                    status="committed",
                    commit_ref=commit_ref,
                    reason="governed dispatch commitment linearized",
                    current_snapshot_digest=current.snapshot_digest,
                )
        except Exception as exc:
            return DispatchCommitDecision(
                status="unavailable",
                reason=f"dispatch commitment failed: {exc}",
            )
