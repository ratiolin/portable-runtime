"""B4-A production graduation for application-bound RecoveryObservation authority."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Event
from portable_runtime.stores.recovery_application_observation import (
    RecoveryApplicationObservationInMemoryStateStore,
    RecoveryApplicationObservationSQLiteStateStore,
)
from portable_runtime.workflows.recovery_application import (
    RecoveryApplicationCommitRequest,
)
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
    application_observation_identity,
    bound_application_ref,
    is_application_completion,
    prepare_recovery_application_observation_commit,
)
from portable_runtime.workflows.recovery_observation import (
    RECOVERY_APPLICATION_OBSERVATION_ROLE,
    RecoveryObservation,
    RecoveryObservationCommitRequest,
    recovery_observation_from_event,
)
from tests.conformance.test_recovery_application_authority import _seed_disposition


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield RecoveryApplicationObservationInMemoryStateStore()
        return
    store = RecoveryApplicationObservationSQLiteStateStore(
        tmp_path / f"recovery-application-observation-{suffix}.db"
    )
    try:
        yield store
    finally:
        store.close()


def _seed_application(
    store: Any,
    *,
    suffix: str,
    action: str = "reconcile-again",
) -> tuple[dict[str, Any], Any]:
    graph, disposition = _seed_disposition(
        store,
        action=action,
        suffix=suffix,
        effect_semantics="reconcilable",
    )
    application = store.commit_recovery_application(
        RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    )
    return graph, application


def _request(
    application_ref: str,
    *,
    status: str = "reported-unknown",
    provenance_refs: tuple[str, ...] = (),
) -> RecoveryApplicationObservationCommitRequest:
    return RecoveryApplicationObservationCommitRequest(
        recovery_application_ref=application_ref,
        observation_source="provider-reconcile",
        reported_status=status,  # type: ignore[arg-type]
        provenance_refs=provenance_refs,
    )


def _legacy_observation_event() -> Event:
    return Event(
        id="recovery_observation_legacy",
        type="RecoveryObservationRecorded",
        subject_ref="dispatch:legacy",
        payload={
            "schema": "recovery-observation-v1",
            "semantic_level": "recovery-observation",
            "authoritative_outcome": False,
            "observation_instance_ref": "legacy-instance",
            "dispatch_commit_ref": "dispatch:legacy",
            "action_ref": "action:legacy",
            "attempt_ref": "attempt:legacy",
            "step_ref": "step:legacy",
            "request_ref": "request:legacy",
            "provider_id": "provider:legacy",
            "idempotency_key": None,
            "observation_source": "provider-reconcile",
            "reported_status": "reported-unknown",
            "provenance_refs": ["recovery_application_looks_like_a_ref"],
        },
    )


def test_ab_generic_request_remains_unbound_while_observation_decoder_is_compatible() -> None:
    assert set(RecoveryObservationCommitRequest.__dataclass_fields__) == {
        "observation_instance_ref",
        "dispatch_commit_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }
    assert "recovery_application_ref" in RecoveryObservation.__dataclass_fields__
    legacy = recovery_observation_from_event(_legacy_observation_event())
    assert legacy.recovery_application_ref is None


def test_ab_001_opaque_provenance_is_not_application_authority() -> None:
    legacy = recovery_observation_from_event(_legacy_observation_event())
    assert is_application_completion(legacy) is False
    assert bound_application_ref(legacy) is None


def test_ab_002_bound_request_surface_is_application_plus_result_only() -> None:
    fields = set(RecoveryApplicationObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }
    assert "dispatch_commit_ref" not in fields
    assert "observation_instance_ref" not in fields


def test_ab_003_missing_or_forged_application_fails_closed() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    with pytest.raises(ValueError, match="RecoveryApplication|application|durable"):
        prepare_recovery_application_observation_commit(
            store,
            _request("recovery_application:forged"),
        )


def test_ab_004_wrong_application_kind_fails_closed() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(
        store,
        suffix="wrong-kind",
        action="hold-unresolved",
    )
    with pytest.raises(ValueError, match="reconciliation-request|kind|application"):
        store.commit_recovery_application_observation(_request(application.id))


def test_ab_005_mismatched_application_dispatch_graph_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(store, suffix="graph-rebound")
    original_get_event = store.get_event
    durable = original_get_event(application.id)
    assert durable is not None
    payload = dict(durable.payload)
    payload["source_dispatch_ref"] = "dispatch:other"
    forged = durable.model_copy(update={"payload": payload})

    def _get_event(event_id: str) -> Event | None:
        if event_id == application.id:
            return forged
        return original_get_event(event_id)

    monkeypatch.setattr(store, "get_event", _get_event)
    with pytest.raises(ValueError, match="rebound|dispatch|binding"):
        prepare_recovery_application_observation_commit(
            store,
            _request(application.id),
        )


def test_ab_006_legacy_unbound_observation_is_not_completion() -> None:
    legacy = recovery_observation_from_event(_legacy_observation_event())
    assert legacy.observation_source == "provider-reconcile"
    assert legacy.provenance_refs == ("recovery_application_looks_like_a_ref",)
    assert legacy.recovery_application_ref is None
    assert is_application_completion(legacy) is False


def test_ab_007_application_derives_stable_observation_identity() -> None:
    first = application_observation_identity("recovery_application:A")
    second = application_observation_identity("recovery_application:A")
    other = application_observation_identity("recovery_application:B")
    assert first == second
    assert first != other


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_ab_008_same_application_same_semantics_replays(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"replay-{backend}") as store:
        _graph, application = _seed_application(
            store,
            suffix=f"replay-{backend}",
        )
        request = _request(application.id, status="reported-succeeded")
        first = store.commit_recovery_application_observation(request)
        replay = store.commit_recovery_application_observation(request)
        assert replay == first
        assert replay.recovery_application_ref == application.id
        assert replay.id == application_observation_identity(application.id)
        events = [event for event in store.list_events() if event.id == first.id]
        assert len(events) == 1


def test_ab_009_same_application_changed_report_is_rebound() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(store, suffix="status-rebound")
    store.commit_recovery_application_observation(
        _request(application.id, status="reported-succeeded")
    )
    with pytest.raises(ValueError, match="rebound|identity|semantics"):
        store.commit_recovery_application_observation(
            _request(application.id, status="reported-failed")
        )


def test_ab_010_same_application_cannot_accumulate_second_completion() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(store, suffix="provenance-rebound")
    first = store.commit_recovery_application_observation(
        _request(
            application.id,
            provenance_refs=("provider-report:1",),
        )
    )
    with pytest.raises(ValueError, match="rebound|identity|semantics"):
        store.commit_recovery_application_observation(
            _request(
                application.id,
                provenance_refs=("provider-report:2",),
            )
        )
    assert store.get_recovery_application_observation(application.id) == first


def test_ab_011_bound_observation_is_execution_level_only() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(store, suffix="execution-level")
    before_types = [event.type for event in store.list_events()]
    observation = store.commit_recovery_application_observation(
        _request(application.id, status="reported-succeeded")
    )
    after_types = [event.type for event in store.list_events()]
    assert observation.authoritative_outcome is False
    assert observation.recovery_application_ref == application.id
    assert after_types.count("RecoveryDispositionRecorded") == before_types.count(
        "RecoveryDispositionRecorded"
    )
    assert after_types.count("RecoveryApplicationRecorded") == before_types.count(
        "RecoveryApplicationRecorded"
    )


def test_ab_012_bound_commit_has_no_follow_on_or_execution_authority() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    graph, application = _seed_application(store, suffix="stop")
    attempts_before = [attempt.id for attempt in store.list_attempts(graph["step"].id)]
    events_before = list(store.list_events())
    store.commit_recovery_application_observation(_request(application.id))
    events_after = list(store.list_events())
    assert [attempt.id for attempt in store.list_attempts(graph["step"].id)] == attempts_before
    assert len(events_after) == len(events_before) + 1
    added = {event.id for event in events_after} - {event.id for event in events_before}
    assert added == {application_observation_identity(application.id)}
    assert not hasattr(store, "reconcile_recovery_application")
    assert not hasattr(store, "retry_recovery_application")


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_ab_013_direct_bound_event_append_is_denied(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"direct-{backend}") as store:
        _graph, application = _seed_application(
            store,
            suffix=f"direct-{backend}",
        )
        prepared = prepare_recovery_application_observation_commit(
            store,
            _request(application.id),
        )
        with pytest.raises(ValueError, match="RecoveryObservation|commit_recovery_observation"):
            store.append_event(prepared.event)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_ab_014_serialized_bound_observation_import_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"import-{backend}") as store:
        _graph, application = _seed_application(
            store,
            suffix=f"import-{backend}",
        )
        prepared = prepare_recovery_application_observation_commit(
            store,
            _request(application.id),
        )
        state = {"event": [prepared.event.model_dump(mode="json")]}
        with pytest.raises(ValueError, match="P5|import|RecoveryObservation"):
            store.import_state(state)


def test_ab_bound_event_carries_first_class_role_and_application_ref() -> None:
    store = RecoveryApplicationObservationInMemoryStateStore()
    _graph, application = _seed_application(store, suffix="payload")
    observation = store.commit_recovery_application_observation(_request(application.id))
    event = store.get_event(observation.id)
    assert event is not None
    assert event.subject_ref == application.id
    assert event.payload["observation_role"] == RECOVERY_APPLICATION_OBSERVATION_ROLE
    assert event.payload["recovery_application_ref"] == application.id


def test_ab_sqlite_replays_after_close_reopen(tmp_path: Path) -> None:
    path = tmp_path / "application-observation-reopen.db"
    first_store = RecoveryApplicationObservationSQLiteStateStore(path)
    try:
        _graph, application = _seed_application(first_store, suffix="sqlite-reopen")
        request = _request(application.id, status="reported-succeeded")
        first = first_store.commit_recovery_application_observation(request)
    finally:
        first_store.close()

    reopened = RecoveryApplicationObservationSQLiteStateStore(path)
    try:
        replay = reopened.commit_recovery_application_observation(request)
        assert replay == first
        assert reopened.get_recovery_application_observation(application.id) == first
    finally:
        reopened.close()
