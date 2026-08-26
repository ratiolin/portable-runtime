"""B4-P4a conformance for durable, non-executing RecoveryApplication authority."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Event
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows import recovery_application as application_module
from portable_runtime.workflows.recovery_application import (
    RecoveryApplicationCommitRequest,
)
from portable_runtime.workflows.recovery_disposition import RecoveryDispositionCommitRequest
from tests.conformance.test_recovery_disposition_counterexamples import (
    _Policy,
    _observe,
    _seed_subject,
)


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"recovery-application-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_disposition(
    store: Any,
    *,
    action: str,
    suffix: str,
    effect_semantics: str | None = None,
) -> tuple[dict[str, Any], Any]:
    graph = _seed_subject(store, suffix)
    if effect_semantics is not None:
        step = store.get_step(graph["step"].id)
        assert step is not None
        step = step.model_copy(
            update={
                "effect_semantics": effect_semantics,
                "side_effect_class": effect_semantics,
            }
        )
        store.save_step(step)
        graph["step"] = step
    observation = _observe(store, graph, instance_ref=f"obs:p4a:{suffix}")
    disposition = store.commit_recovery_disposition(
        RecoveryDispositionCommitRequest(
            dispatch_commit_ref=str(graph["dispatch_ref"]),
            observation_refs=(observation.id,),
            outcome_refs=(),
            policy_ref="policy:recovery:p4a",
        ),
        policy=_Policy(action),
    )
    return graph, disposition


def test_p4a_request_surface_is_exact_disposition_only() -> None:
    assert set(RecoveryApplicationCommitRequest.__dataclass_fields__) == {"disposition_ref"}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p4a_same_disposition_commits_and_replays_one_application(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"replay-{backend}") as store:
        _graph, disposition = _seed_disposition(
            store,
            action="hold-unresolved",
            suffix=f"replay-{backend}",
        )
        request = RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
        first = store.commit_recovery_application(request)
        replay = store.commit_recovery_application(request)
        assert replay == first
        event = store.get_event(first.id)
        assert event is not None
        assert event.type == "RecoveryApplicationRecorded"
        assert event.subject_ref == disposition.id


def test_p4a_sqlite_replays_after_close_reopen(tmp_path: Path) -> None:
    path = tmp_path / "recovery-application-reopen.db"
    first_store = SQLiteStateStore(path)
    try:
        _graph, disposition = _seed_disposition(
            first_store,
            action="reconcile-again",
            suffix="sqlite-reopen",
        )
        request = RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
        first = first_store.commit_recovery_application(request)
    finally:
        first_store.close()

    reopened = SQLiteStateStore(path)
    try:
        replay = reopened.commit_recovery_application(request)
        assert replay == first
        assert replay.application_kind == "reconciliation-request"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("action", "effect_semantics", "expected_kind"),
    [
        ("hold-unresolved", "reconcilable", "hold"),
        ("reconcile-again", "reconcilable", "reconciliation-request"),
        ("retry-idempotent", "idempotent", "retry-request"),
        ("require-manual-resolution", "reconcilable", "manual-resolution-handoff"),
        ("accept-objective-resolution", "reconcilable", "objective-resolution-acceptance"),
    ],
)
def test_p4a_application_kind_is_store_derived(
    action: str,
    effect_semantics: str,
    expected_kind: str,
) -> None:
    store = InMemoryStateStore()
    _graph, disposition = _seed_disposition(
        store,
        action=action,
        effect_semantics=effect_semantics,
        suffix=f"kind-{action}",
    )
    application = store.commit_recovery_application(
        RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    )
    assert application.application_kind == expected_kind


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p4a_retry_intent_preserves_provenance_without_execution_authority(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"retry-{backend}") as store:
        graph, disposition = _seed_disposition(
            store,
            action="retry-idempotent",
            effect_semantics="idempotent",
            suffix=f"retry-{backend}",
        )
        attempts_before = [attempt.id for attempt in store.list_attempts(graph["step"].id)]
        step_before = store.get_step(graph["step"].id)
        action_before = store.get_action(graph["action"].id)

        application = store.commit_recovery_application(
            RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
        )

        assert application.application_kind == "retry-request"
        assert application.source_dispatch_ref == graph["dispatch_ref"]
        assert application.source_attempt_ref == graph["attempt"].id
        assert application.source_step_ref == graph["step"].id
        assert application.source_action_ref == graph["action"].id
        assert application.source_request_ref == graph["action"].request_ref
        assert application.source_provider_id == graph["action"].provider_id
        assert application.source_run_ref == graph["run"].id
        assert application.source_work_ref == graph["work"].id
        assert application.idempotency_key == graph["attempt"].idempotency_key
        assert [attempt.id for attempt in store.list_attempts(graph["step"].id)] == attempts_before
        assert store.get_step(graph["step"].id) == step_before
        assert store.get_action(graph["action"].id) == action_before
        assert not hasattr(application, "attempt_ref")
        assert not hasattr(application, "invocation_permit_ref")
        assert not hasattr(application, "new_dispatch_commit_ref")


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p4a_direct_application_event_append_is_denied(
    backend: str,
    tmp_path: Path,
) -> None:
    with (
        _store(backend, tmp_path, f"forged-{backend}") as store,
        pytest.raises(ValueError, match="RecoveryApplication|commit_recovery_application"),
    ):
        store.append_event(
            Event(
                id="recovery_application_forged",
                type="RecoveryApplicationRecorded",
                subject_ref="recovery_disposition:forged",
                payload={
                    "schema": "recovery-application-v1",
                    "semantic_level": "recovery-application",
                    "disposition_ref": "recovery_disposition:forged",
                    "application_kind": "hold",
                },
            )
        )


def test_p4a_same_identity_changed_derived_semantics_is_rebound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryStateStore()
    _graph, disposition = _seed_disposition(
        store,
        action="hold-unresolved",
        suffix="semantic-rebound",
    )
    request = RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    first = store.commit_recovery_application(request)
    assert first.application_kind == "hold"

    monkeypatch.setitem(
        application_module._APPLICATION_KIND_BY_ACTION,
        "hold-unresolved",
        "manual-resolution-handoff",
    )
    with pytest.raises(ValueError, match="rebound"):
        store.commit_recovery_application(request)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p4a_serialized_application_authority_import_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"import-{backend}") as store:
        state = {
            "event": [
                Event(
                    id="recovery_application_imported",
                    type="RecoveryApplicationRecorded",
                    subject_ref="recovery_disposition:imported",
                    payload={
                        "schema": "recovery-application-v1",
                        "semantic_level": "recovery-application",
                        "disposition_ref": "recovery_disposition:imported",
                        "application_kind": "hold",
                    },
                ).model_dump(mode="json")
            ]
        }
        with pytest.raises(ValueError, match="P5 RecoveryApplication authority import is unsupported"):
            store.import_state(state)


def test_p4a_retry_materialization_api_remains_absent() -> None:
    assert not hasattr(application_module, "prepare_recovery_retry_request")
