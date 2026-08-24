"""Atomic, append-only audit for in-place Assertion qualification changes.

The event records a runtime-native before/after transition.  It is not a B0
certificate and grants no authority.  The subsequent semantic write still has
to pass the existing Revision/AuthorizationUse mutation authority gate.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from portable_runtime.core.models import Event, new_id
from portable_runtime.records.models import Assertion

QUALIFICATION_TRANSITION_EVENT_TYPE = "qualification.status.changed"
QUALIFICATION_TRANSITION_SCHEMA = "qualification-transition-v1"


def qualification_transition_snapshot(value: Assertion) -> dict[str, Any]:
    return {
        "id": value.id,
        "record_type": value.record_type,
        "lifecycle_status": value.lifecycle_status,
        "epistemic_status": value.epistemic_status,
        "version": value.version,
    }


def _normalize_reason_refs(reason_refs: Iterable[str]) -> list[str]:
    refs = list(dict.fromkeys(str(ref).strip() for ref in reason_refs if str(ref).strip()))
    if not refs:
        raise ValueError("qualification transition requires at least one reason_ref")
    return refs


def build_qualification_transition_event(
    before: Assertion,
    after: Assertion,
    *,
    reason_refs: Iterable[str],
    event_id: str | None = None,
) -> Event:
    if before.id != after.id:
        raise ValueError("qualification transition must preserve Assertion identity")
    if before.record_type != "Assertion" or after.record_type != "Assertion":
        raise ValueError("qualification transition only applies to Assertion records")
    if before.statement != after.statement:
        raise ValueError("qualification transition cannot change the asserted proposition")
    if before.lifecycle_status != after.lifecycle_status:
        raise ValueError("qualification transition cannot bundle a lifecycle transition")
    if before.epistemic_status == after.epistemic_status:
        raise ValueError("qualification transition requires an epistemic_status change")
    if after.version != before.version + 1:
        raise ValueError("qualification transition must advance version by exactly one")
    refs = _normalize_reason_refs(reason_refs)
    return Event(
        id=event_id or new_id("event"),
        type=QUALIFICATION_TRANSITION_EVENT_TYPE,
        subject_ref=after.id,
        payload={
            "schema_version": QUALIFICATION_TRANSITION_SCHEMA,
            "before": qualification_transition_snapshot(before),
            "after": qualification_transition_snapshot(after),
            "reason_refs": refs,
        },
    )


def commit_qualification_transition(
    store: Any,
    after: Assertion,
    *,
    expected_version: int,
    reason_refs: Iterable[str],
    event_id: str | None = None,
) -> Event:
    """Atomically append transition evidence and persist the authorized update."""

    with store.transaction():
        before = store.get_record(after.id)
        if not isinstance(before, Assertion):
            raise ValueError(f"qualification transition subject {after.id!r} is not an Assertion")
        if before.version != expected_version:
            raise ValueError(
                f"qualification transition expected version {expected_version}, current is {before.version}"
            )
        event = build_qualification_transition_event(
            before,
            after,
            reason_refs=reason_refs,
            event_id=event_id,
        )
        store.append_event(event)
        # Existing semantic mutation authorization remains authoritative.  If
        # it rejects the update, the outer store transaction also rolls back
        # the event, so audit and current state cannot diverge.
        store.save_record(after)
    return event


__all__ = [
    "QUALIFICATION_TRANSITION_EVENT_TYPE",
    "QUALIFICATION_TRANSITION_SCHEMA",
    "qualification_transition_snapshot",
    "build_qualification_transition_event",
    "commit_qualification_transition",
]
