"""B4-P3b conformance for store-owned durable RecoveryDisposition commits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.recovery_disposition import RecoveryDispositionCommitRequest
from tests.conformance.test_recovery_disposition_counterexamples import (
    _NeverPolicy,
    _Policy,
    _observe,
    _seed_subject,
)


def _request(graph: dict[str, Any], observation_ref: str) -> RecoveryDispositionCommitRequest:
    return RecoveryDispositionCommitRequest(
        dispatch_commit_ref=str(graph["dispatch_ref"]),
        observation_refs=(observation_ref,),
        outcome_refs=(),
        policy_ref="policy:recovery:v1",
    )


def test_p3b_sqlite_exact_basis_replays_after_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "p3b-reopen.db"
    first_store = SQLiteStateStore(path)
    try:
        graph = _seed_subject(first_store, "p3b-reopen")
        observation = _observe(first_store, graph, instance_ref="obs:p3b:reopen")
        request = _request(graph, observation.id)
        first_policy = _Policy("hold-unresolved")
        first = first_store.commit_recovery_disposition(request, policy=first_policy)
        assert first_policy.calls == 1
    finally:
        first_store.close()

    reopened = SQLiteStateStore(path)
    try:
        current_policy = _NeverPolicy()
        replay = reopened.commit_recovery_disposition(request, policy=current_policy)
        assert replay == first
        assert current_policy.calls == 0
        event = reopened.get_event(first.id)
        assert event is not None
        assert event.type == "RecoveryDispositionRecorded"
    finally:
        reopened.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3b_policy_failure_leaves_no_disposition_event(
    backend: str,
    tmp_path: Path,
) -> None:
    store: Any
    if backend == "memory":
        store = InMemoryStateStore()
    else:
        store = SQLiteStateStore(tmp_path / "p3b-policy-failure.db")
    try:
        graph = _seed_subject(store, f"p3b-policy-failure-{backend}")
        observation = _observe(store, graph, instance_ref=f"obs:p3b:failure:{backend}")
        request = _request(graph, observation.id)

        class FailingPolicy:
            def decide(self, basis: Any) -> str:
                raise RuntimeError("policy failed")

        before = [event.id for event in store.list_events()]
        with pytest.raises(RuntimeError, match="policy failed"):
            store.commit_recovery_disposition(request, policy=FailingPolicy())
        after = [event.id for event in store.list_events()]
        assert after == before
    finally:
        if isinstance(store, SQLiteStateStore):
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3b_append_failure_rolls_back_disposition_event(
    backend: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store: Any
    if backend == "memory":
        store = InMemoryStateStore()
    else:
        store = SQLiteStateStore(tmp_path / "p3b-append-failure.db")
    try:
        graph = _seed_subject(store, f"p3b-append-failure-{backend}")
        observation = _observe(store, graph, instance_ref=f"obs:p3b:append:{backend}")
        request = _request(graph, observation.id)
        original_append = store.append_event

        def fail_after_append(event: Any) -> None:
            original_append(event)
            if getattr(event, "type", "") == "RecoveryDispositionRecorded":
                raise RuntimeError("injected append failure")

        monkeypatch.setattr(store, "append_event", fail_after_append)
        before = [event.id for event in store.list_events()]
        with pytest.raises(RuntimeError, match="injected append failure"):
            store.commit_recovery_disposition(request, policy=_Policy("hold-unresolved"))
        after = [event.id for event in store.list_events()]
        assert after == before
    finally:
        if isinstance(store, SQLiteStateStore):
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_p3b_commit_does_not_create_follow_on_execution_state(
    backend: str,
    tmp_path: Path,
) -> None:
    store: Any
    if backend == "memory":
        store = InMemoryStateStore()
    else:
        store = SQLiteStateStore(tmp_path / "p3b-non-executing.db")
    try:
        graph = _seed_subject(store, f"p3b-non-executing-{backend}")
        observation = _observe(store, graph, instance_ref=f"obs:p3b:non-exec:{backend}")
        request = _request(graph, observation.id)
        attempts_before = [attempt.id for attempt in store.list_attempts(graph["step"].id)]
        action_before = store.get_action(graph["action"].id)
        step_before = store.get_step(graph["step"].id)

        store.commit_recovery_disposition(request, policy=_Policy("retry-idempotent"))

        attempts_after = [attempt.id for attempt in store.list_attempts(graph["step"].id)]
        assert attempts_after == attempts_before
        assert store.get_action(graph["action"].id) == action_before
        assert store.get_step(graph["step"].id) == step_before
    finally:
        if isinstance(store, SQLiteStateStore):
            store.close()
