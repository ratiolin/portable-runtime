"""Durable, non-executing RecoveryApplication authority.

A RecoveryApplication is one store-owned orchestration intent derived from one
exact durable RecoveryDisposition. This module does not create requests,
Attempts, InvocationPermits, dispatch commitments, provider calls, terminal
completion, or governance discharge.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from portable_runtime.core.models import Event, StepAttempt
from portable_runtime.workflows.recovery_disposition import (
    RecoveryDisposition,
    RecoveryDispositionCommitRequest,
    RecoveryDispositionStoreReader,
    reconstruct_recovery_disposition_basis,
    recovery_disposition_from_event,
)

RECOVERY_APPLICATION_EVENT = "RecoveryApplicationRecorded"
RECOVERY_APPLICATION_SCHEMA = "recovery-application-v1"

RecoveryApplicationKind = Literal[
    "hold",
    "reconciliation-request",
    "retry-request",
    "manual-resolution-handoff",
    "objective-resolution-acceptance",
]

# Schema vocabulary is stable durable decoding state. It must not be inferred
# from the current derivation mapping: mapping drift must surface as semantic
# rebound against a still-decodable historical fact.
_APPLICATION_KINDS = frozenset(
    {
        "hold",
        "reconciliation-request",
        "retry-request",
        "manual-resolution-handoff",
        "objective-resolution-acceptance",
    }
)

_APPLICATION_KIND_BY_ACTION: dict[str, RecoveryApplicationKind] = {
    "hold-unresolved": "hold",
    "reconcile-again": "reconciliation-request",
    "retry-idempotent": "retry-request",
    "require-manual-resolution": "manual-resolution-handoff",
    "accept-objective-resolution": "objective-resolution-acceptance",
}


@dataclass(frozen=True)
class RecoveryApplicationCommitRequest:
    """Caller input is one exact durable RecoveryDisposition identity."""

    disposition_ref: str


@dataclass(frozen=True)
class RecoveryApplication:
    """One durable application intent; never execution authority."""

    id: str
    disposition_ref: str
    application_kind: RecoveryApplicationKind
    source_dispatch_ref: str
    source_attempt_ref: str
    source_step_ref: str
    source_action_ref: str
    source_request_ref: str
    source_provider_id: str
    source_run_ref: str
    source_work_ref: str
    idempotency_key: str | None


@dataclass(frozen=True)
class PreparedRecoveryApplicationCommit:
    application: RecoveryApplication
    event: Event | None
    replayed: bool


class RecoveryApplicationStoreReader(RecoveryDispositionStoreReader, Protocol):
    def get_event(self, event_id: str) -> Event | None: ...
    def get_attempt(self, attempt_id: str) -> StepAttempt | None: ...


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _application_id(disposition_ref: str) -> str:
    payload = {
        "schema": RECOVERY_APPLICATION_SCHEMA,
        "disposition_ref": disposition_ref,
    }
    return f"recovery_application_{hashlib.sha256(_canonical(payload).encode()).hexdigest()}"


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RecoveryApplication requires {label}")
    return value.strip()


def _kind_from_disposition(disposition: RecoveryDisposition) -> RecoveryApplicationKind:
    try:
        return _APPLICATION_KIND_BY_ACTION[disposition.action]
    except KeyError as exc:
        raise ValueError("RecoveryApplication disposition action is unsupported") from exc


def _reconstruct_source(
    store: RecoveryApplicationStoreReader,
    disposition_ref: str,
) -> tuple[RecoveryDisposition, Any, StepAttempt]:
    event = store.get_event(disposition_ref)
    if event is None or event.id != disposition_ref:
        raise ValueError("RecoveryApplication requires exact durable RecoveryDisposition")
    disposition = recovery_disposition_from_event(event)
    request = RecoveryDispositionCommitRequest(
        dispatch_commit_ref=disposition.dispatch_commit_ref,
        observation_refs=disposition.observation_refs,
        outcome_refs=disposition.outcome_refs,
        policy_ref=disposition.policy_ref,
    )
    basis = reconstruct_recovery_disposition_basis(store, request)
    if basis.basis_key != disposition.basis_key:
        raise ValueError("RecoveryApplication source disposition basis rebound")
    attempt = store.get_attempt(basis.attempt_ref)
    if attempt is None or attempt.id != basis.attempt_ref:
        raise ValueError("RecoveryApplication requires exact source StepAttempt")
    return disposition, basis, attempt


def _prepare_application(
    store: RecoveryApplicationStoreReader,
    disposition_ref: str,
) -> RecoveryApplication:
    disposition, basis, attempt = _reconstruct_source(store, disposition_ref)
    kind = _kind_from_disposition(disposition)
    idempotency_key = attempt.idempotency_key if kind == "retry-request" else None
    if kind == "retry-request" and (not isinstance(idempotency_key, str) or not idempotency_key):
        raise ValueError("RecoveryApplication retry intent requires source idempotency identity")
    return RecoveryApplication(
        id=_application_id(disposition_ref),
        disposition_ref=disposition_ref,
        application_kind=kind,
        source_dispatch_ref=basis.dispatch_commit_ref,
        source_attempt_ref=basis.attempt_ref,
        source_step_ref=basis.step_ref,
        source_action_ref=basis.action_ref,
        source_request_ref=basis.request_ref,
        source_provider_id=basis.provider_id,
        source_run_ref=basis.run_ref,
        source_work_ref=basis.work_ref,
        idempotency_key=idempotency_key,
    )


def _event_for(application: RecoveryApplication) -> Event:
    return Event(
        id=application.id,
        type=RECOVERY_APPLICATION_EVENT,
        subject_ref=application.disposition_ref,
        payload={
            "schema": RECOVERY_APPLICATION_SCHEMA,
            "semantic_level": "recovery-application",
            "disposition_ref": application.disposition_ref,
            "application_kind": application.application_kind,
            "source_dispatch_ref": application.source_dispatch_ref,
            "source_attempt_ref": application.source_attempt_ref,
            "source_step_ref": application.source_step_ref,
            "source_action_ref": application.source_action_ref,
            "source_request_ref": application.source_request_ref,
            "source_provider_id": application.source_provider_id,
            "source_run_ref": application.source_run_ref,
            "source_work_ref": application.source_work_ref,
            "idempotency_key": application.idempotency_key,
        },
    )


def recovery_application_from_event(event: Event) -> RecoveryApplication:
    """Decode and verify one durable RecoveryApplicationRecorded fact."""

    if event.type != RECOVERY_APPLICATION_EVENT:
        raise ValueError("event is not a RecoveryApplicationRecorded fact")
    payload = event.payload if isinstance(event.payload, dict) else {}
    if payload.get("schema") != RECOVERY_APPLICATION_SCHEMA:
        raise ValueError("unsupported RecoveryApplication schema")
    if payload.get("semantic_level") != "recovery-application":
        raise ValueError("RecoveryApplication semantic level mismatch")
    disposition_ref = _required_string(payload.get("disposition_ref"), "disposition_ref")
    kind = payload.get("application_kind")
    if kind not in _APPLICATION_KINDS:
        raise ValueError("invalid RecoveryApplication kind")
    expected_id = _application_id(disposition_ref)
    if event.id != expected_id or event.subject_ref != disposition_ref:
        raise ValueError("RecoveryApplication deterministic identity mismatch")
    idempotency_key = payload.get("idempotency_key")
    if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key):
        raise ValueError("invalid RecoveryApplication idempotency identity")
    if kind == "retry-request" and idempotency_key is None:
        raise ValueError("retry RecoveryApplication requires idempotency identity")
    if kind != "retry-request" and idempotency_key is not None:
        raise ValueError("non-retry RecoveryApplication cannot carry idempotency identity")
    return RecoveryApplication(
        id=event.id,
        disposition_ref=disposition_ref,
        application_kind=cast(RecoveryApplicationKind, kind),
        source_dispatch_ref=_required_string(payload.get("source_dispatch_ref"), "source_dispatch_ref"),
        source_attempt_ref=_required_string(payload.get("source_attempt_ref"), "source_attempt_ref"),
        source_step_ref=_required_string(payload.get("source_step_ref"), "source_step_ref"),
        source_action_ref=_required_string(payload.get("source_action_ref"), "source_action_ref"),
        source_request_ref=_required_string(payload.get("source_request_ref"), "source_request_ref"),
        source_provider_id=_required_string(payload.get("source_provider_id"), "source_provider_id"),
        source_run_ref=_required_string(payload.get("source_run_ref"), "source_run_ref"),
        source_work_ref=_required_string(payload.get("source_work_ref"), "source_work_ref"),
        idempotency_key=cast(str | None, idempotency_key),
    )


def _semantic_payload(value: RecoveryApplication | Event) -> dict[str, object]:
    application = recovery_application_from_event(value) if isinstance(value, Event) else value
    return {
        "id": application.id,
        "disposition_ref": application.disposition_ref,
        "application_kind": application.application_kind,
        "source_dispatch_ref": application.source_dispatch_ref,
        "source_attempt_ref": application.source_attempt_ref,
        "source_step_ref": application.source_step_ref,
        "source_action_ref": application.source_action_ref,
        "source_request_ref": application.source_request_ref,
        "source_provider_id": application.source_provider_id,
        "source_run_ref": application.source_run_ref,
        "source_work_ref": application.source_work_ref,
        "idempotency_key": application.idempotency_key,
    }


def same_recovery_application_semantics(
    left: RecoveryApplication | Event,
    right: RecoveryApplication | Event,
) -> bool:
    """Compare authority semantics without timestamp noise."""

    try:
        return _semantic_payload(left) == _semantic_payload(right)
    except (TypeError, ValueError):
        return False


def prepare_recovery_application_commit(
    store: RecoveryApplicationStoreReader,
    request: RecoveryApplicationCommitRequest,
) -> PreparedRecoveryApplicationCommit:
    """Prepare or replay one exact-disposition durable application intent."""

    disposition_ref = _required_string(request.disposition_ref, "disposition_ref")
    expected = _prepare_application(store, disposition_ref)
    existing = store.get_event(expected.id)
    if existing is not None:
        durable = recovery_application_from_event(existing)
        if not same_recovery_application_semantics(durable, expected):
            raise ValueError("RecoveryApplication identity semantics rebound")
        return PreparedRecoveryApplicationCommit(
            application=durable,
            event=None,
            replayed=True,
        )
    return PreparedRecoveryApplicationCommit(
        application=expected,
        event=_event_for(expected),
        replayed=False,
    )
