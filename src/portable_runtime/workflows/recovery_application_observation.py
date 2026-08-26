"""Store-prepared application-bound RecoveryObservation authority.

This module is deliberately non-executing. It converts one exact durable
RecoveryApplication(kind=reconciliation-request) plus a reported observation
fact into one deterministic, application-bound RecoveryObservation. It never
calls providers, creates attempts/permits/dispatches, or changes recovery
disposition/application state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from portable_runtime.core.models import Event
from portable_runtime.workflows.recovery_application import (
    RecoveryApplication,
    RecoveryApplicationCommitRequest,
    RecoveryApplicationStoreReader,
    prepare_recovery_application_commit,
    recovery_application_from_event,
)
from portable_runtime.workflows.recovery_observation import (
    RECOVERY_APPLICATION_OBSERVATION_ROLE,
    RecoveryObservation,
    RecoveryObservationCommitRequest,
    RecoveryReportedStatus,
    PreparedRecoveryObservationCommit,
    prepare_recovery_observation_commit,
    recovery_application_observation_identity,
    recovery_application_observation_instance_ref,
    recovery_observation_from_event,
)


@dataclass(frozen=True)
class RecoveryApplicationObservationCommitRequest:
    """Caller supplies only exact application identity and reported observation fact."""

    recovery_application_ref: str
    observation_source: str
    reported_status: RecoveryReportedStatus
    provenance_refs: tuple[str, ...] = ()


class RecoveryApplicationObservationStoreReader(
    RecoveryApplicationStoreReader,
    Protocol,
):
    def get_event(self, event_id: str) -> Event | None: ...


def application_observation_identity(recovery_application_ref: str) -> str:
    return recovery_application_observation_identity(recovery_application_ref)


def is_application_completion(observation: RecoveryObservation) -> bool:
    return observation.recovery_application_ref is not None


def bound_application_ref(observation: RecoveryObservation) -> str | None:
    return observation.recovery_application_ref


def _exact_application(
    store: RecoveryApplicationObservationStoreReader,
    application_ref: str,
) -> RecoveryApplication:
    ref = application_ref.strip()
    if not ref:
        raise ValueError("application-bound RecoveryObservation requires recovery_application_ref")
    event = store.get_event(ref)
    if event is None or event.id != ref:
        raise ValueError("application-bound RecoveryObservation requires exact durable RecoveryApplication")
    application = recovery_application_from_event(event)
    replay = prepare_recovery_application_commit(
        store,
        RecoveryApplicationCommitRequest(disposition_ref=application.disposition_ref),
    )
    if replay.application.id != ref or not replay.replayed:
        raise ValueError("application-bound RecoveryObservation source application rebound")
    if application != replay.application:
        raise ValueError("application-bound RecoveryObservation application semantics rebound")
    if application.application_kind != "reconciliation-request":
        raise ValueError(
            "application-bound RecoveryObservation requires reconciliation-request application kind"
        )
    return application


def _assert_application_graph(
    application: RecoveryApplication,
    observation: RecoveryObservation,
) -> None:
    exact = {
        "dispatch": (application.source_dispatch_ref, observation.dispatch_commit_ref),
        "attempt": (application.source_attempt_ref, observation.attempt_ref),
        "step": (application.source_step_ref, observation.step_ref),
        "action": (application.source_action_ref, observation.action_ref),
        "request": (application.source_request_ref, observation.request_ref),
        "provider": (application.source_provider_id, observation.provider_id),
    }
    mismatched = [name for name, (left, right) in exact.items() if left != right]
    if mismatched:
        raise ValueError(
            "application-bound RecoveryObservation source graph rebound: "
            + ", ".join(mismatched)
        )


def prepare_recovery_application_observation_commit(
    store: RecoveryApplicationObservationStoreReader,
    request: RecoveryApplicationObservationCommitRequest,
) -> PreparedRecoveryObservationCommit:
    """Prepare one deterministic completion observation for one exact application."""

    application = _exact_application(store, request.recovery_application_ref)
    source = request.observation_source.strip()
    if not source:
        raise ValueError("application-bound RecoveryObservation requires observation_source")

    generic = prepare_recovery_observation_commit(
        store,
        RecoveryObservationCommitRequest(
            observation_instance_ref=recovery_application_observation_instance_ref(
                application.id
            ),
            dispatch_commit_ref=application.source_dispatch_ref,
            observation_source=source,
            reported_status=request.reported_status,
            provenance_refs=request.provenance_refs,
        ),
    )
    _assert_application_graph(application, generic.observation)

    payload = dict(generic.event.payload)
    payload["observation_role"] = RECOVERY_APPLICATION_OBSERVATION_ROLE
    payload["recovery_application_ref"] = application.id
    event = Event(
        id=recovery_application_observation_identity(application.id),
        type=generic.event.type,
        subject_ref=application.id,
        payload=payload,
    )
    return PreparedRecoveryObservationCommit(
        observation=recovery_observation_from_event(event),
        event=event,
    )
