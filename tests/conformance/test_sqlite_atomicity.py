"""Executable SQLite CAS/lease atomicity conformance (S001-S006)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from portable_runtime.core.models import Run, Step, Work, new_id
from portable_runtime.stores.sqlite import CASExecutionError, SQLiteStateStore


def _seed_step(path: Path, *, version: int = 3) -> tuple[SQLiteStateStore, Work, Run, Step]:
    store = SQLiteStateStore(path)
    work = Work(id=new_id("work"), title="atomicity", kind="generic-task")
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    step = Step(
        id=new_id("step"),
        run_id=run.id,
        step_key="atomic",
        status="pending",
        version=version,
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    return store, work, run, step


def _seed_run(path: Path, *, generation: int = 0) -> tuple[SQLiteStateStore, Run]:
    store = SQLiteStateStore(path)
    work = Work(id=new_id("work"), title="lease", kind="generic-task")
    run = Run(
        id=new_id("run"),
        work_id=work.id,
        status="running",
        lease_generation=generation,
    )
    store.save_work(work)
    store.save_run(run)
    return store, run


def test_s001_cas_success(tmp_path: Path) -> None:
    """A CAS at the current version commits exactly one next state."""

    store, _work, _run, step = _seed_step(tmp_path / "s001.db")
    try:
        replacement = step.model_copy(update={"status": "running", "version": 4})
        assert store.compare_and_swap("step", step.id, expected_version=3, new_value=replacement) is True
        current = store.get_step(step.id)
        assert current is not None
        assert current.version == 4
        assert current.status == "running"
    finally:
        store.close()


def test_s002_cas_stale_conflict_two_connections(tmp_path: Path) -> None:
    """Two readers of version 3 cannot both commit a version-4 replacement."""

    path = tmp_path / "s002.db"
    writer, _work, _run, step = _seed_step(path)
    reader = SQLiteStateStore(path)
    try:
        # Both connections observe the same version before either writes.
        assert writer.get_step(step.id).version == 3
        assert reader.get_step(step.id).version == 3

        winner_state = step.model_copy(update={"status": "running", "version": 4})
        stale_state = step.model_copy(update={"status": "failed", "version": 4})
        assert writer.compare_and_swap("step", step.id, expected_version=3, new_value=winner_state) is True
        assert reader.compare_and_swap("step", step.id, expected_version=3, new_value=stale_state) is False

        current = reader.get_step(step.id)
        assert current is not None
        assert current.status == "running"
        assert current.version == 4
    finally:
        reader.close()
        writer.close()


def test_s003_cas_database_error_is_typed(tmp_path: Path) -> None:
    """Malformed SQL is an execution error, not a false version conflict."""

    store, _work, _run, step = _seed_step(tmp_path / "s003.db")
    try:
        store._CAS_UPDATE_SQL = "UPDATE runtime_records SET data=? WHERE BROKEN"  # type: ignore[attr-defined]
        replacement = step.model_copy(update={"version": 4})
        with pytest.raises(CASExecutionError):
            store.compare_and_swap("step", step.id, expected_version=3, new_value=replacement)
        # The failed transaction leaves the original state untouched.
        current = store.get_step(step.id)
        assert current is not None
        assert current.version == 3
    finally:
        store.close()


def test_s004_lease_acquire_race_two_connections(tmp_path: Path) -> None:
    """Concurrent acquire transactions have exactly one winner."""

    path = tmp_path / "s004.db"
    first, run = _seed_run(path)
    second = SQLiteStateStore(path)
    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}

    def acquire(name: str, store: SQLiteStateStore) -> None:
        barrier.wait(timeout=5)
        results[name] = store.acquire_lease(run.id, owner=name, ttl_seconds=30)

    t1 = threading.Thread(target=acquire, args=("A", first))
    t2 = threading.Thread(target=acquire, args=("B", second))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    try:
        assert not t1.is_alive() and not t2.is_alive()
        assert results.keys() == {"A", "B"}
        assert sum(results.values()) == 1
        current = first.get_run(run.id)
        assert current is not None
        assert current.lease_generation == 1
        assert current.lease_owner in {"A", "B"}
    finally:
        second.close()
        first.close()


def test_s005_lease_takeover_increments_generation(tmp_path: Path) -> None:
    """An expired generation-7 lease is taken over as generation 8."""

    path = tmp_path / "s005.db"
    first, run = _seed_run(path, generation=6)
    second = SQLiteStateStore(path)
    try:
        assert first.acquire_lease(run.id, owner="A", ttl_seconds=0.05) is True
        owned = first.get_run(run.id)
        assert owned is not None
        assert owned.lease_owner == "A"
        assert owned.lease_generation == 7

        time.sleep(0.12)
        assert second.acquire_lease(run.id, owner="B", ttl_seconds=30) is True
        taken_over = first.get_run(run.id)
        assert taken_over is not None
        assert taken_over.lease_owner == "B"
        assert taken_over.lease_generation == 8
    finally:
        second.close()
        first.close()


def test_s006_stale_owner_cannot_renew_after_takeover(tmp_path: Path) -> None:
    """The old owner cannot revive generation 7 after B owns generation 8."""

    path = tmp_path / "s006.db"
    first, run = _seed_run(path, generation=6)
    second = SQLiteStateStore(path)
    try:
        assert first.acquire_lease(run.id, owner="A", ttl_seconds=0.05) is True
        time.sleep(0.12)
        assert second.acquire_lease(run.id, owner="B", ttl_seconds=30) is True
        assert first.renew_lease(run.id, owner="A", ttl_seconds=30) is False
        assert second.renew_lease(run.id, owner="B", ttl_seconds=30) is True
        current = first.get_run(run.id)
        assert current is not None
        assert current.lease_owner == "B"
        assert current.lease_generation == 8
    finally:
        second.close()
        first.close()
