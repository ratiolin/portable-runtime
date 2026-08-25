from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.records.verified_outcome_commit import VerifiedOutcomeCommitRequest
from portable_runtime.records.verified_outcome_replay import (
    VerifiedOutcomeAuthorityHistoryError,
    validate_verified_outcome_authority_graph,
)
from portable_runtime.stores.bundle import export_bundle, import_bundle
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ("patch:v1",)
_AUTHORITY_TYPES = {"ObjectiveVerificationAccepted", "OutcomeConfirmed"}


@contextmanager
def _store(
    backend: str,
    tmp_path: Path,
    suffix: str,
) -> Iterator[InMemoryStateStore | SQLiteStateStore]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"p5-import-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_verified(store: Any, suffix: str) -> OutcomeRecord:
    work = Work(id=f"work_p5_{suffix}", title="P5 verified import")
    run = Run(id=f"run_p5_{suffix}", work_id=work.id, status="running")
    step = Step(id=f"step_p5_{suffix}", run_id=run.id, step_key="effect", status="succeeded")
    attempt = StepAttempt(
        id=f"attempt_p5_{suffix}",
        step_id=step.id,
        provider_id="executor",
        request_ref=f"request_p5_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_p5_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref=attempt.request_ref,
        status="succeeded",
    )
    proof = EvidenceArtifact(
        id=f"evidence_p5_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        metadata={
            "verification_result": {"result": "pass"},
            "proof_class": "objective-verification",
            "action_ref": action.id,
            "request_id": action.request_ref,
            "attempt_ref": attempt.id,
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": dict(_SCOPE),
            "subject_version_refs": list(_VERSIONS),
            "obligation_refs": ["verify.effect"],
            "verifier_provenance": {
                "provider_id": "verifier",
                "verifier_id": "verifier:objective",
                "method": "closed-verification",
            },
        },
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    store.save_record(proof)
    return store.commit_verified_outcome(
        VerifiedOutcomeCommitRequest(
            action_ref=action.id,
            evidence_refs=(proof.id,),
            expected_work_id=work.id,
            expected_run_id=run.id,
            expected_request_id=action.request_ref,
            expected_attempt_ref=attempt.id,
            verification_scope=dict(_SCOPE),
            subject_version_refs=_VERSIONS,
        )
    )


def _find(state: dict[str, list[dict[str, object]]], kind: str, identifier: str) -> dict[str, object]:
    return next(value for value in state[kind] if value.get("id") == identifier)


def _authority_event_ids(state: dict[str, list[dict[str, object]]], outcome_id: str) -> set[str]:
    return {
        str(event["id"])
        for event in state["event"]
        if event.get("type") in _AUTHORITY_TYPES and event.get("subject_ref") == outcome_id
    }


@pytest.mark.parametrize(
    ("source_backend", "target_backend"),
    [
        ("memory", "memory"),
        ("memory", "sqlite"),
        ("sqlite", "memory"),
        ("sqlite", "sqlite"),
    ],
)
@pytest.mark.parametrize("transport", ["state", "bundle"])
def test_p5_2_verified_outcome_four_way_portability(
    source_backend: str,
    target_backend: str,
    transport: str,
    tmp_path: Path,
) -> None:
    suffix = f"{source_backend}_{target_backend}_{transport}"
    bundle_path = tmp_path / f"{suffix}.tar"
    with _store(source_backend, tmp_path, f"source-{suffix}") as source:
        outcome = _seed_verified(source, suffix)
        expected_state = source.export_state()
        expected_digest = outcome.metadata["verification_binding_digest"]
        expected_event_ids = _authority_event_ids(expected_state, outcome.id)
        if transport == "state":
            payload = deepcopy(expected_state)
        else:
            export_bundle(source, None, bundle_path, runtime_id=f"p5-{suffix}")
            payload = None

    with _store(target_backend, tmp_path, f"target-{suffix}") as target:
        if transport == "state":
            assert payload is not None
            target.import_state(payload)
        else:
            import_bundle(target, None, bundle_path)
        imported = target.get_record(outcome.id)
        assert isinstance(imported, OutcomeRecord)
        assert imported.lifecycle_status == "confirmed"
        assert imported.id == outcome.id
        assert imported.metadata["verification_binding_digest"] == expected_digest
        imported_state = target.export_state()
        assert _authority_event_ids(imported_state, outcome.id) == expected_event_ids
        replayed = validate_verified_outcome_authority_graph(imported_state)
        assert len(replayed) == 1
        assert replayed[0].outcome.id == outcome.id
        assert replayed[0].binding_digest == expected_digest


def _corrupt(
    state: dict[str, list[dict[str, object]]],
    outcome: OutcomeRecord,
    corruption: str,
) -> None:
    raw_outcome = _find(state, "record", outcome.id)
    metadata = dict(raw_outcome["metadata"])  # type: ignore[arg-type]
    events = [event for event in state["event"] if event.get("subject_ref") == outcome.id]
    if corruption == "outcome-id":
        raw_outcome["id"] = f"{outcome.id}_forged"
    elif corruption == "binding-digest":
        metadata["verification_binding_digest"] = "forged-binding-digest"
        raw_outcome["metadata"] = metadata
    elif corruption == "objective-result":
        metadata["objective_result"] = "fail"
        raw_outcome["metadata"] = metadata
    elif corruption == "action-ref":
        raw_outcome["action_ref"] = "action_missing"
    elif corruption == "attempt-ref":
        metadata["attempt_ref"] = "attempt_missing"
        raw_outcome["metadata"] = metadata
    elif corruption == "scope":
        metadata["verification_scope"] = {"resource": "repo/other", "operation": "effect"}
        raw_outcome["metadata"] = metadata
    elif corruption == "version":
        metadata["subject_version_refs"] = ["patch:v2"]
        raw_outcome["metadata"] = metadata
    elif corruption == "evidence-ref":
        raw_outcome["evidence_refs"] = ["evidence_missing"]
    elif corruption == "event-id":
        events[0]["id"] = f"{events[0]['id']}_forged"
    elif corruption == "event-payload":
        payload = dict(events[0]["payload"])  # type: ignore[arg-type]
        payload["verification_binding_digest"] = "forged-event-digest"
        events[0]["payload"] = payload
    elif corruption == "remove-event":
        state["event"].remove(events[0])
    elif corruption == "orphan-event":
        orphan = deepcopy(events[0])
        orphan["id"] = f"{events[0]['id']}_orphan"
        state["event"].append(orphan)
    else:
        raise AssertionError(f"unknown corruption {corruption}")


@pytest.mark.parametrize("target_backend", ["memory", "sqlite"])
@pytest.mark.parametrize(
    "corruption",
    [
        "outcome-id",
        "binding-digest",
        "objective-result",
        "action-ref",
        "attempt-ref",
        "scope",
        "version",
        "evidence-ref",
        "event-id",
        "event-payload",
        "remove-event",
        "orphan-event",
    ],
)
def test_p5_2_forged_import_fails_atomically(
    target_backend: str,
    corruption: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    outcome = _seed_verified(source, f"corrupt_{corruption}")
    forged = deepcopy(source.export_state())
    _corrupt(forged, outcome, corruption)

    with _store(target_backend, tmp_path, f"atomic-{target_backend}-{corruption}") as target:
        sentinel = Work(id=f"sentinel_{target_backend}_{corruption}", title="must survive failed import")
        target.save_work(sentinel)
        before = target.export_state()
        with pytest.raises(ValueError):
            target.import_state(forged)
        assert target.export_state() == before
        assert target.get_work(sentinel.id) is not None
        assert target.get_record(outcome.id) is None


@pytest.mark.parametrize("target_backend", ["memory", "sqlite"])
def test_p5_2_historical_confirmed_outcome_without_authority_graph_is_incompatible(
    target_backend: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    outcome = _seed_verified(source, f"historical_{target_backend}")
    incompatible = deepcopy(source.export_state())
    incompatible["event"] = [
        event
        for event in incompatible["event"]
        if not (event.get("type") in _AUTHORITY_TYPES and event.get("subject_ref") == outcome.id)
    ]
    with _store(target_backend, tmp_path, f"historical-target-{target_backend}") as target:
        with pytest.raises(
            VerifiedOutcomeAuthorityHistoryError,
            match="incompatible confirmed-outcome authority history",
        ):
            target.import_state(incompatible)
        assert target.get_record(outcome.id) is None


@pytest.mark.parametrize("target_backend", ["memory", "sqlite"])
def test_p5_2_recorded_outcome_import_remains_non_authoritative(
    target_backend: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    work = Work(id=f"work_recorded_{target_backend}", title="recorded import")
    run = Run(id=f"run_recorded_{target_backend}", work_id=work.id, status="running")
    action = Action(
        id=f"action_recorded_{target_backend}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref=f"request_recorded_{target_backend}",
        status="succeeded",
    )
    recorded = OutcomeRecord(
        id=f"outcome_recorded_{target_backend}",
        action_ref=action.id,
        lifecycle_status="recorded",
        metadata={"objective_result": "pass"},
    )
    source.save_work(work)
    source.save_run(run)
    source.save_action(action)
    source.save_record(recorded)
    with _store(target_backend, tmp_path, f"recorded-target-{target_backend}") as target:
        target.import_state(source.export_state())
        imported = target.get_record(recorded.id)
        assert isinstance(imported, OutcomeRecord)
        assert imported.lifecycle_status == "recorded"
        assert not any(event.type in _AUTHORITY_TYPES for event in target.list_events())
