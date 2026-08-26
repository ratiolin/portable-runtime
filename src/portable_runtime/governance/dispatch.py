from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, cast

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Event
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.provider_execution_binding import ProviderExecutionBinding
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
    provider_execution_binding_ref: str | None = None


class DispatchLinearizationError(RuntimeError):
    """The authoritative StateStore cannot provide a linearized write scope."""


@contextmanager
def _dispatch_linearized_write(store: Any) -> Iterator[None]:
    """Serialize governance truth and dispatch commitment in one store domain."""

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
    provider_execution_binding_ref: str | None = None,
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
    # Preserve exact legacy dispatch identities when no execution binding was
    # captured. New reality-exit dispatches include the binding ref in identity.
    if provider_execution_binding_ref is not None:
        payload["provider_execution_binding_ref"] = provider_execution_binding_ref
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"dispatch_{hashlib.sha256(raw.encode()).hexdigest()}"


def dispatch_recovery_mode(step: Any, attempt: Any) -> DispatchRecoveryMode:
    """Classify recovery after a durable dispatch commitment."""

    metadata = getattr(attempt, "metadata", {})
    if not isinstance(metadata, dict) or not metadata.get("dispatch_commit_ref"):
        return "uncommitted"
    semantics = str(getattr(step, "effect_semantics", ""))
    if semantics in {"pure", "idempotent", "deduplicatable"}:
        return "idempotent-retry"
    if semantics == "reconcilable":
        return "reconcile"
    return "unknown"


class GovernanceDispatchCommitter:
    """Linearize one governed dispatch claim against canonical governance.

    When an authoritative ProviderRegistry is supplied, the exact configured
    execution binding is captured inside the same durable dispatch commitment
    before provider reality exit. The binding is provenance only and grants no
    provider capability.
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
        provider_registry: Any | None = None,
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

                execution_binding: ProviderExecutionBinding | None = None
                if provider_registry is not None:
                    binding_getter = getattr(provider_registry, "execution_binding", None)
                    if not callable(binding_getter):
                        raise DispatchLinearizationError(
                            "authoritative provider registry lacks execution binding authority"
                        )
                    execution_binding = binding_getter(permit.provider_id)
                    if execution_binding.provider_id != permit.provider_id:
                        raise DispatchLinearizationError(
                            "provider execution binding does not match InvocationPermit provider"
                        )

                binding_ref = execution_binding.id if execution_binding is not None else None
                commit_ref = _dispatch_commit_ref(
                    request,
                    permit,
                    attempt_id,
                    binding_ref,
                )
                event_payload: dict[str, Any] = {
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
                }
                if execution_binding is not None:
                    event_payload["provider_execution_binding_ref"] = execution_binding.id
                    event_payload["provider_execution_binding"] = execution_binding.model_dump(mode="json")
                event = Event(
                    id=commit_ref,
                    type=DISPATCH_COMMIT_EVENT,
                    subject_ref=request.id,
                    payload=event_payload,
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
                    if execution_binding is not None:
                        metadata["provider_execution_binding_ref"] = execution_binding.id
                    self.store.save_attempt(
                        attempt.model_copy(update={"metadata": metadata})
                    )

                self.store.append_event(event)
                return DispatchCommitDecision(
                    status="committed",
                    commit_ref=commit_ref,
                    reason="governed dispatch commitment linearized",
                    current_snapshot_digest=current.snapshot_digest,
                    provider_execution_binding_ref=binding_ref,
                )
        except Exception as exc:
            return DispatchCommitDecision(
                status="unavailable",
                reason=f"dispatch commitment failed: {exc}",
            )
