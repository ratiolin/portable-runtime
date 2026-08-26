"""Store-owned commit planning for durable RecoveryDisposition facts.

The planner performs exact-basis lookup before any policy execution.  Concrete
stores remain responsible for writer serialization and the guarded event append.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from portable_runtime.core.models import Event
from portable_runtime.workflows.recovery_disposition import (
    RecoveryDisposition,
    RecoveryDispositionAction,
    RecoveryDispositionCommitRequest,
    RecoveryDispositionStoreReader,
    prepare_recovery_disposition,
    reconstruct_recovery_disposition_basis,
    recovery_disposition_from_event,
)

_ALLOWED_ACTIONS = frozenset(
    {
        "hold-unresolved",
        "reconcile-again",
        "retry-idempotent",
        "require-manual-resolution",
        "accept-objective-resolution",
    }
)


@dataclass(frozen=True)
class RecoveryDispositionCommitPlan:
    disposition: RecoveryDisposition
    event: Event | None
    replayed: bool


def _declared_policy_action(policy: Any) -> RecoveryDispositionAction | None:
    """Read an optional static policy declaration without executing policy.

    Exact-basis durable replay always wins over current policy execution.  A
    policy object may expose a static ``action`` declaration; when present it
    is safe to compare that declaration with the durable semantics and reject
    an explicit same-identity rebound without invoking the policy.
    """

    value = getattr(policy, "action", None)
    if value is None:
        return None
    if not isinstance(value, str) or value not in _ALLOWED_ACTIONS:
        raise ValueError("recovery disposition policy declares unsupported action")
    return cast(RecoveryDispositionAction, value)


def prepare_recovery_disposition_commit(
    store: RecoveryDispositionStoreReader,
    request: RecoveryDispositionCommitRequest,
    policy: Any,
) -> RecoveryDispositionCommitPlan:
    """Prepare a new disposition or replay an exact durable basis identity."""

    basis = reconstruct_recovery_disposition_basis(store, request)
    disposition_id = f"recovery_disposition_{basis.basis_key[:32]}"
    existing = store.get_event(disposition_id)
    if existing is not None:
        durable = recovery_disposition_from_event(existing)
        if durable.basis_key != basis.basis_key:
            raise ValueError("RecoveryDisposition deterministic identity rebound")
        declared = _declared_policy_action(policy)
        if declared is not None and declared != durable.action:
            raise ValueError("RecoveryDisposition identity semantics rebound")
        return RecoveryDispositionCommitPlan(
            disposition=durable,
            event=None,
            replayed=True,
        )

    prepared = prepare_recovery_disposition(basis, policy)
    return RecoveryDispositionCommitPlan(
        disposition=prepared.disposition,
        event=prepared.event,
        replayed=False,
    )
