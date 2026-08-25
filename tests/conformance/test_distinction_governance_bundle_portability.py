from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.governance.canonical import (
    GOVERNANCE_HISTORY_SCHEMA,
    GovernanceHistoryVersionError,
    reconstruct_governance_history,
)
from portable_runtime.governance.distinction import DistinctionState, grant_authority
from portable_runtime.governance.history_epoch import detect_governance_history_epoch
from portable_runtime.governance.persistence import (
    GOVERNANCE_APPLICATION_KIND,
    GOVERNANCE_STATE_KIND,
    DistinctionGovernancePersistence,
    InMemoryDistinctionGovernancePersistence,
    PersistedDistinctionState,
    PersistedGovernedApplication,
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


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=1,
    )


def _inject_legacy_state(
    persistence: DistinctionGovernancePersistence,
    *,
    incomplete: bool,
) -> None:
    state = _state()
    with persistence._transaction():
        persistence._put_model(
            GOVERNANCE_STATE_KIND,
            PersistedDistinctionState(
                id="d",
                scheme_id="d",
                qualification=state.qualification,
                activation=state.activation,
                scope=state.scope,
                partition=state.partition,
                version=state.version,
            ),
        )
        if incomplete:
            persistence._put_model(
                GOVERNANCE_APPLICATION_KIND,
                PersistedGovernedApplication(
                    id="legacy-discharge",
                    actor="closer",
                    operation="apply_review_discharge",
                    scheme_id="d",
                    target="review_obligation:q-old",
                    decision_ref="dec-old",
                    context="ctx",
                    review_obligation_id="q-old",
                    effect_kind="review_discharge",
                    pre_anchor="q-old",
                    post_anchor="",
                ),
            )


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_011_bundle_carries_canonical_history_not_sidecar(
    backend: str,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / f"governance-{backend}.tar"
    with _backend(backend, tmp_path, suffix="source") as (source, persistence):
        state = _state()
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

        assert target_persistence.list_states() == {}
        assert target_persistence.list_obligations() == {}
        governance_events = [
            event
            for event in target.list_events()
            if event.type.startswith("governance.distinction.")
        ]
        assert governance_events
        assert all(
            event.payload.get("schema_version") == GOVERNANCE_HISTORY_SCHEMA
            for event in governance_events
        )
        assert detect_governance_history_epoch(target_persistence).epoch == "CANONICAL"

        rebuilt = target_persistence.rebuild_projection_from_canonical_history()
        assert rebuilt == expected
        assert target_persistence.processed_event_obligation_ids("event-bundle") is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_012_history_epoch_detection_never_guesses_missing_provenance(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="empty") as (_store, persistence):
        assert detect_governance_history_epoch(persistence).epoch == "EMPTY"

    with _backend(backend, tmp_path, suffix="provable") as (_store, persistence):
        _inject_legacy_state(persistence, incomplete=False)
        assert detect_governance_history_epoch(persistence).epoch == "LEGACY_PROVABLE"

    with _backend(backend, tmp_path, suffix="incomplete") as (_store, persistence):
        _inject_legacy_state(persistence, incomplete=True)
        status = detect_governance_history_epoch(persistence)
        assert status.epoch == "LEGACY_INCOMPLETE"
        assert "provenance" in status.reason

    with _backend(backend, tmp_path, suffix="canonical") as (store, persistence):
        persistence.seed_state("d", _state())
        status = detect_governance_history_epoch(persistence)
        assert status.epoch == "CANONICAL"
        event = next(
            event
            for event in store.list_events()
            if event.type.startswith("governance.distinction.")
        )
        future_payload = dict(event.payload)
        future_payload["schema_version"] = "distinction-governance-history-v999"
        future = event.model_copy(update={"payload": future_payload})
        with pytest.raises(GovernanceHistoryVersionError, match="unsupported governance history schema"):
            reconstruct_governance_history([future])
