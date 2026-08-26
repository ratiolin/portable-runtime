"""F1-B4 P0 counterexamples for durable RecoveryObservation authority."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"recovery-observation-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


def _dispatch_ref(payload: dict[str, object]) -> str:
    identity = {
        "schema": payload["schema"],
        "request_id": payload["request_id"],
        "provider_id": payload["provider_id"],
        "attempt_id": payload["attempt_ref"],
        "invocation_permit_digest": payload["invocation_permit_digest"],
        "governance_requirement_digest": payload["governance_requirement_digest"],
        "governance_snapshot_digest": payload["governance_snapshot_digest"],
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return f"dispatch_{hashlib.sha256(raw.encode()).hexdigest()}"


def _seed_dispatch_graph(store: Any, suffix: str) -> dict[str, str]:
    work = Work(id=f"work_recovery_{suffix}", title="recovery observation")
    run = Run(id=f"run_recovery_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_recovery_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="unknown",
        current_attempt=1,
        effect_semantics="reconcilable",
        side_effect_class="reconcilable",
    )
    request_ref = f"request_recovery_{suffix}"
    provider_id = "provider:reconcile"
    action = Action(
        id=f"action_recovery_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="deploy.apply",
        provider_id=provider_id,
        request_ref=request_ref,
        status="unknown",
    )
    attempt = StepAttempt(
        id=f"attempt_recovery_{suffix}",
        step_id=step.id,
        attempt_no=1,
        provider_id=provider_id,
        request_ref=request_ref,
        idempotency_key=f"idempotency:{suffix}",
        status="unknown",
        metadata={"action_ref": action.id},
    )
    payload: dict[str, object] = {
        "schema": "governance-dispatch-commit-v1",
        "request_id": request_ref,
        "provider_id": provider_id,
        "attempt_ref": attempt.id,
        "invocation_permit_digest": f"permit:{suffix}",
        "qualification_digest": f"qualification:{suffix}",
        "governance_requirement_digest": f"requirement:{suffix}",
        "governance_snapshot_digest": f"snapshot:{suffix}",
        "lease_generation": 0,
        "linearization_domain": "authoritative-state-store",
    }
    dispatch_ref = _dispatch_ref(payload)
    attempt.metadata.update(
        {
            "dispatch_commit_ref": dispatch_ref,
            "invocation_permit_digest": payload["invocation_permit_digest"],
            "governance_requirement_digest": payload["governance_requirement_digest"],
            "governance_snapshot_digest": payload["governance_snapshot_digest"],
        }
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    store.append_event(
        Event(
            id=dispatch_ref,
            type="InvocationDispatchCommitted",
            subject_ref=request_ref,
            payload=payload,
        )
    )
    return {
        "work_id": work.id,
        "run_id": run.id,
        "step_id": step.id,
        "attempt_id": attempt.id,
        "action_id": action.id,
        "request_ref": request_ref,
        "provider_id": provider_id,
        "dispatch_ref": dispatch_ref,
    }


def _request(module: Any, *, dispatch_ref: str, instance_ref: str, status: str = "reported-succeeded") -> Any:
    return module.RecoveryObservationCommitRequest(
        observation_instance_ref=instance_ref,
        dispatch_commit_ref=dispatch_ref,
        observation_source="provider-reconcile",
        reported_status=status,
        provenance_refs=("provider:reconcile",),
    )


@pytest.mark.xfail(strict=True, reason="B4-P1: durable RecoveryObservation is not implemented")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_001_reported_success_becomes_durable_non_objective_observation(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    with _store(backend, tmp_path, f"reported-success-{backend}") as store:
        graph = _seed_dispatch_graph(store, f"reported-success-{backend}")
        observation = store.commit_recovery_observation(
            _request(
                module,
                dispatch_ref=graph["dispatch_ref"],
                instance_ref=f"observation-instance:{backend}:1",
            )
        )
        assert observation.reported_status == "reported-succeeded"
        assert observation.dispatch_commit_ref == graph["dispatch_ref"]
        assert observation.action_ref == graph["action_id"]
        assert observation.attempt_ref == graph["attempt_id"]
        assert observation.step_ref == graph["step_id"]
        assert observation.request_ref == graph["request_ref"]
        assert observation.provider_id == graph["provider_id"]
        assert observation.authoritative_outcome is False
        assert store.list_records("Outcome") == []
        assert store.get_work(graph["work_id"]).status != "completed"
        assert store.get_run(graph["run_id"]).status != "succeeded"


@pytest.mark.xfail(strict=True, reason="B4-P1: RecoveryObservation replay identity is not implemented")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_002_same_observation_instance_replay_is_idempotent(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    with _store(backend, tmp_path, f"same-instance-{backend}") as store:
        graph = _seed_dispatch_graph(store, f"same-instance-{backend}")
        request = _request(
            module,
            dispatch_ref=graph["dispatch_ref"],
            instance_ref="observation-instance:same",
        )
        first = store.commit_recovery_observation(request)
        second = store.commit_recovery_observation(request)
        assert second.id == first.id
        events = [
            event
            for event in store.list_events(graph["dispatch_ref"])
            if event.type == "RecoveryObservationRecorded"
        ]
        assert [event.id for event in events] == [first.id]


@pytest.mark.xfail(strict=True, reason="B4-P1: observation instance identity is not implemented")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_003_same_report_new_instance_is_new_recovery_fact(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    with _store(backend, tmp_path, f"new-instance-{backend}") as store:
        graph = _seed_dispatch_graph(store, f"new-instance-{backend}")
        first = store.commit_recovery_observation(
            _request(
                module,
                dispatch_ref=graph["dispatch_ref"],
                instance_ref="observation-instance:one",
            )
        )
        second = store.commit_recovery_observation(
            _request(
                module,
                dispatch_ref=graph["dispatch_ref"],
                instance_ref="observation-instance:two",
            )
        )
        assert second.id != first.id
        events = [
            event
            for event in store.list_events(graph["dispatch_ref"])
            if event.type == "RecoveryObservationRecorded"
        ]
        assert {event.id for event in events} == {first.id, second.id}


@pytest.mark.xfail(strict=True, reason="B4-P1: dispatch/action graph validation is not implemented")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_004_wrong_action_binding_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    with _store(backend, tmp_path, f"wrong-action-{backend}") as store:
        graph = _seed_dispatch_graph(store, f"wrong-action-{backend}")
        attempt = store.get_attempt(graph["attempt_id"])
        assert attempt is not None
        store.save_attempt(
            attempt.model_copy(
                update={"metadata": {**attempt.metadata, "action_ref": "action:forged"}}
            )
        )
        with pytest.raises(ValueError, match="action|dispatch|binding"):
            store.commit_recovery_observation(
                _request(
                    module,
                    dispatch_ref=graph["dispatch_ref"],
                    instance_ref="observation-instance:forged-action",
                )
            )
        assert not any(event.type == "RecoveryObservationRecorded" for event in store.list_events())


@pytest.mark.xfail(strict=True, reason="B4-P1: direct RecoveryObservation event bypass is not closed")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_005_direct_recovery_observation_event_append_is_denied(
    backend: str,
    tmp_path: Path,
) -> None:
    with (
        _store(backend, tmp_path, f"direct-event-{backend}") as store,
        pytest.raises(ValueError, match="RecoveryObservation|commit_recovery_observation"),
    ):
        store.append_event(
            Event(
                id=f"recovery_observation_forged_{backend}",
                type="RecoveryObservationRecorded",
                subject_ref="dispatch:forged",
                payload={
                    "schema": "recovery-observation-v1",
                    "reported_status": "reported-succeeded",
                    "authoritative_outcome": False,
                },
            )
        )


@pytest.mark.xfail(strict=True, reason="B4-P1: same observation instance rebound protection is not implemented")
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b4_p1_006_same_instance_cannot_be_rebound_to_new_report(
    backend: str,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    with _store(backend, tmp_path, f"rebound-{backend}") as store:
        graph = _seed_dispatch_graph(store, f"rebound-{backend}")
        store.commit_recovery_observation(
            _request(
                module,
                dispatch_ref=graph["dispatch_ref"],
                instance_ref="observation-instance:stable",
                status="reported-succeeded",
            )
        )
        with pytest.raises(ValueError, match="rebound|append-only|identity"):
            store.commit_recovery_observation(
                _request(
                    module,
                    dispatch_ref=graph["dispatch_ref"],
                    instance_ref="observation-instance:stable",
                    status="reported-failed",
                )
            )
