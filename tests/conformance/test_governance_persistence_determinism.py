from __future__ import annotations

from pathlib import Path

from portable_runtime.governance.distinction import DistinctionState
from portable_runtime.governance.persistence import (
    PersistedDistinctionState,
    SQLiteDistinctionGovernancePersistence,
    _semantic_dump,
)
from portable_runtime.stores.sqlite import SQLiteStateStore


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({f"scope-{index}" for index in range(32)}),
        partition=(
            frozenset({f"scope-{index}" for index in range(16)}),
            frozenset({f"scope-{index}" for index in range(16, 32)}),
        ),
        version=7,
    )


def test_semantic_dump_preserves_unordered_python_value_semantics() -> None:
    state = _state()
    persisted = PersistedDistinctionState(
        id="d",
        scheme_id="d",
        qualification=state.qualification,
        activation=state.activation,
        scope=state.scope,
        partition=state.partition,
        version=state.version,
    )

    semantic = _semantic_dump(persisted)

    assert semantic["scope"] == state.scope
    assert semantic["partition"] == state.partition
    assert isinstance(semantic["scope"], frozenset)
    assert isinstance(semantic["partition"], tuple)


def test_sqlite_exact_state_replay_remains_idempotent_after_round_trip(
    tmp_path: Path,
) -> None:
    path = tmp_path / "governance-replay.db"
    state = _state()

    first_store = SQLiteStateStore(path)
    try:
        SQLiteDistinctionGovernancePersistence(first_store).seed_state("d", state)
    finally:
        first_store.close()

    second_store = SQLiteStateStore(path)
    try:
        persistence = SQLiteDistinctionGovernancePersistence(second_store)
        persistence.seed_state("d", state)
        assert persistence.get_state("d") == state
    finally:
        second_store.close()
