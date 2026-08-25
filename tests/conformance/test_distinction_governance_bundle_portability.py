from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.governance.distinction import DistinctionState, grant_authority
from portable_runtime.governance.persistence import (
    DistinctionGovernancePersistence,
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.revalidation import RevalidationGovernanceLifecycle
from portable_runtime.stores.bundle import export_bundle, import_bundle
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

BACKENDS = ("memory", "sqlite")


@dataclass(frozen=True)
class _Relation:
    id: str
    relation_type: str
    object_ref: str
    subject_ref: str


@contextmanager
def _backend(
    backend: str,
    tmp_path: Path,
    *,
    suffix: str,
) -> Iterator[tuple[Any, DistinctionGovernancePersistence]]:
    if backend == "memory":
        store = InMemoryStateStore()
        yield store, InMemoryDistinctionGovernancePersistence(store)
        return
    store = SQLiteStateStore(tmp_path / f"bundle-{backend}-{suffix}.db")
    try:
        yield store, SQLiteDistinctionGovernancePersistence(store)
    finally:
        store.close()


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_011_bundle_carries_canonical_history_not_sidecar(
    backend: str,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / f"governance-{backend}.tar"
    with _backend(backend, tmp_path, suffix="source") as (source, persistence):
        state = DistinctionState(
            qualification="qualified",
            activation="active",
            scope=frozenset({"a", "b"}),
            partition=(frozenset({"a"}), frozenset({"b"})),
            version=1,
        )
        persistence.seed_state("d", state)
        lifecycle = RevalidationGovernanceLifecycle(
            persistence=persistence,
            authority=grant_authority([]),
            freshness={"model:v2": "model:v2@1"}.get,
        )
        lifecycle.observe_change(
            event_ref="event-bundle",
            change_ref="model:v2",
            change_type="model",
            relations=[_Relation("rel-1", "validated-under", "model:v2", "d")],
            context="ctx",
        )
        expected = lifecycle.snapshot()
        export_bundle(source, None, bundle_path, runtime_id="governance-portability")

    with _backend(backend, tmp_path, suffix="target") as (target, target_persistence):
        import_bundle(target, None, bundle_path)

        # The private sidecar is not a bundle kind. Canonical events are.
        assert target_persistence.list_states() == {}
        assert target_persistence.list_obligations() == {}
        assert any(
            event.type.startswith("governance.distinction.")
            for event in target.list_events()
        )

        rebuilt = target_persistence.rebuild_projection_from_canonical_history()
        assert rebuilt == expected
        assert target_persistence.processed_event_obligation_ids("event-bundle") is not None
