from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from portable_runtime.governance.distinction import (
    APPLY_QUALIFICATION,
    APPLY_REVIEW_DISCHARGE,
    DECIDE_QUALIFICATION,
    DECIDE_REVIEW,
    ApplicationReceipt,
    DistinctionState,
    GovernanceDecision,
    GovernedApplication,
    ReviewObligation,
    candidate_state_effect,
    obligations_anchor,
    state_anchor,
)
from portable_runtime.governance.persistence import (
    GOVERNANCE_APPLICATION_KIND,
    GOVERNANCE_KINDS,
    DistinctionGovernancePersistence,
    GovernancePersistenceError,
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

BACKENDS = ("memory", "sqlite")


@contextmanager
def _store(
    backend: str,
    tmp_path: Path,
) -> Iterator[tuple[DistinctionGovernancePersistence, InMemoryStateStore | SQLiteStateStore]]:
    if backend == "memory":
        backing = InMemoryStateStore()
        yield InMemoryDistinctionGovernancePersistence(backing), backing
        return
    backing = SQLiteStateStore(tmp_path / "governance.db")
    try:
        yield SQLiteDistinctionGovernancePersistence(backing), backing
    finally:
        backing.close()


def _state(version: int = 10) -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=version,
    )


def _obligation(qid: str = "q1", trigger: str = "event-1") -> ReviewObligation:
    return ReviewObligation(
        id=qid,
        target="d",
        trigger_ref=trigger,
        basis_refs=("evidence",),
        context="ctx",
        blocking=True,
        closure_requirements=frozenset({"basis_checked"}),
    )


def _review_decision(state: DistinctionState, did: str = "dec-review") -> GovernanceDecision:
    return GovernanceDecision(
        id=did,
        actor="reviewer",
        operation=DECIDE_REVIEW,
        target="d",
        context="ctx",
        review_refs=("q1",),
        disposition="no_change",
        expected_state_anchor=state_anchor(state),
        basis_anchors=(("evidence", "evidence:v1"),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
    )


def _qualification_decision(state: DistinctionState, did: str = "dec-q") -> GovernanceDecision:
    return GovernanceDecision(
        id=did,
        actor="reviewer",
        operation=DECIDE_QUALIFICATION,
        target="d",
        context="ctx",
        review_refs=("q1",),
        disposition="transition_required",
        expected_state_anchor=state_anchor(state),
        basis_anchors=(("evidence", "evidence:v1"),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
        required_qualification="qualified",
        required_activation="suspended",
    )


def _state_receipt(
    state: DistinctionState,
    decision: GovernanceDecision,
    app_id: str = "app-state",
) -> tuple[DistinctionState, ApplicationReceipt]:
    application = GovernedApplication(
        id=app_id,
        actor="operator",
        operation=APPLY_QUALIFICATION,
        scheme_id="d",
        target="d",
        decision_ref=decision.id,
        context="ctx",
        new_qualification="qualified",
        new_activation="suspended",
    )
    next_state = candidate_state_effect(application, state)
    return next_state, ApplicationReceipt(
        application=application,
        effect_kind="state",
        pre_anchor=state_anchor(state),
        post_anchor=state_anchor(next_state),
    )


def _discharge_receipt(
    obligation: ReviewObligation,
    decision: GovernanceDecision,
    app_id: str = "app-discharge",
) -> ApplicationReceipt:
    application = GovernedApplication(
        id=app_id,
        actor="closer",
        operation=APPLY_REVIEW_DISCHARGE,
        scheme_id="d",
        target=f"review_obligation:{obligation.id}",
        decision_ref=decision.id,
        context="ctx",
        review_obligation_id=obligation.id,
    )
    return ApplicationReceipt(
        application=application,
        effect_kind="review_discharge",
        pre_anchor=obligations_anchor({obligation.id: obligation}),
        post_anchor=obligations_anchor({}),
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_p001_state_seed_is_idempotent_but_not_an_update(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        store.seed_state("d", state)
        store.seed_state("d", state)
        assert store.get_state("d") == state
        with pytest.raises(GovernancePersistenceError, match="governed transitions"):
            store.seed_state("d", replace(state, version=11))
        assert store.get_state("d") == state


@pytest.mark.parametrize("backend", BACKENDS)
def test_p002_equivalent_open_obligation_cannot_be_duplicated(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        first = _obligation("q1", "event-1")
        replay_with_new_id = _obligation("q2", "event-1")
        store.open_obligation(first)
        store.open_obligation(first)
        with pytest.raises(GovernancePersistenceError, match="equivalent review obligation"):
            store.open_obligation(replay_with_new_id)
        assert store.list_obligations() == {"q1": first}


@pytest.mark.parametrize("backend", BACKENDS)
def test_p003_decision_identity_is_immutable_and_exact_replay_idempotent(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        obligation = _obligation()
        decision = _review_decision(state)
        store.seed_state("d", state)
        store.open_obligation(obligation)
        store.record_decision(decision)
        store.record_decision(decision)
        assert store.get_decision(decision.id) == decision
        with pytest.raises(GovernancePersistenceError, match="cannot be rebound"):
            store.record_decision(replace(decision, disposition="transition_required"))
        assert store.get_decision(decision.id) == decision


@pytest.mark.parametrize("backend", BACKENDS)
def test_p004_decision_must_match_durable_open_review_input(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        store.seed_state("d", state)
        store.open_obligation(_obligation())
        mismatched = replace(_review_decision(state), context="other")
        with pytest.raises(GovernancePersistenceError, match="does not match"):
            store.record_decision(mismatched)
        assert store.get_decision(mismatched.id) is None


@pytest.mark.parametrize("backend", BACKENDS)
def test_p005_state_effect_and_application_receipt_commit_atomically(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        obligation = _obligation()
        decision = _qualification_decision(state)
        store.seed_state("d", state)
        store.open_obligation(obligation)
        store.record_decision(decision)
        next_state, receipt = _state_receipt(state, decision)

        store.commit_state_application("d", next_state, receipt)

        assert store.get_state("d") == next_state
        assert store.get_application(receipt.application.id) == receipt
        assert store.get_obligation(obligation.id) == obligation


@pytest.mark.parametrize("backend", BACKENDS)
def test_p006_application_id_cannot_be_replayed_or_rebound(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        decision = _qualification_decision(state)
        store.seed_state("d", state)
        store.open_obligation(_obligation())
        store.record_decision(decision)
        next_state, receipt = _state_receipt(state, decision)
        store.commit_state_application("d", next_state, receipt)

        with pytest.raises(GovernancePersistenceError, match="immutable"):
            store.commit_state_application("d", next_state, receipt)


@pytest.mark.parametrize("backend", BACKENDS)
def test_p007_state_write_rolls_back_if_application_receipt_write_fails(
    backend: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        decision = _qualification_decision(state)
        store.seed_state("d", state)
        store.open_obligation(_obligation())
        store.record_decision(decision)
        next_state, receipt = _state_receipt(state, decision)
        original_put = store._put_model

        def fail_receipt(kind: str, value: object) -> None:
            if kind == GOVERNANCE_APPLICATION_KIND:
                raise RuntimeError("injected receipt failure")
            original_put(kind, value)  # type: ignore[arg-type]

        monkeypatch.setattr(store, "_put_model", fail_receipt)
        with pytest.raises(RuntimeError, match="injected receipt failure"):
            store.commit_state_application("d", next_state, receipt)

        assert store.get_state("d") == state
        assert store.get_application(receipt.application.id) is None


@pytest.mark.parametrize("backend", BACKENDS)
def test_p008_review_discharge_and_receipt_commit_atomically(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        obligation = _obligation()
        decision = _review_decision(state)
        store.seed_state("d", state)
        store.open_obligation(obligation)
        store.record_decision(decision)
        receipt = _discharge_receipt(obligation, decision)

        store.commit_review_discharge(obligation.id, receipt)

        assert store.get_obligation(obligation.id) is None
        assert store.get_application(receipt.application.id) == receipt
        assert store.get_state("d") == state


@pytest.mark.parametrize("backend", BACKENDS)
def test_p009_review_obligation_delete_rolls_back_if_receipt_write_fails(
    backend: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _store(backend, tmp_path) as (store, _backing):
        state = _state()
        obligation = _obligation()
        decision = _review_decision(state)
        store.seed_state("d", state)
        store.open_obligation(obligation)
        store.record_decision(decision)
        receipt = _discharge_receipt(obligation, decision)
        original_put = store._put_model

        def fail_receipt(kind: str, value: object) -> None:
            if kind == GOVERNANCE_APPLICATION_KIND:
                raise RuntimeError("injected receipt failure")
            original_put(kind, value)  # type: ignore[arg-type]

        monkeypatch.setattr(store, "_put_model", fail_receipt)
        with pytest.raises(RuntimeError, match="injected receipt failure"):
            store.commit_review_discharge(obligation.id, receipt)

        assert store.get_obligation(obligation.id) == obligation
        assert store.get_application(receipt.application.id) is None


@pytest.mark.parametrize("backend", BACKENDS)
def test_p010_private_governance_state_does_not_change_public_export_surface(
    backend: str,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path) as (store, backing):
        store.seed_state("d", _state())
        store.open_obligation(_obligation())
        exported = backing.export_state()
        assert not GOVERNANCE_KINDS.intersection(exported)


def test_p011_sqlite_uses_one_private_generic_table_and_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "durable.db"
    state = _state()
    obligation = _obligation()
    backing = SQLiteStateStore(path)
    try:
        store = SQLiteDistinctionGovernancePersistence(backing)
        store.seed_state("d", state)
        store.open_obligation(obligation)
    finally:
        backing.close()

    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'runtime_governance%'"
            ).fetchall()
        }
        assert tables == {"runtime_governance_records"}
    finally:
        connection.close()

    reopened = SQLiteStateStore(path)
    try:
        store = SQLiteDistinctionGovernancePersistence(reopened)
        assert store.get_state("d") == state
        assert store.get_obligation(obligation.id) == obligation
    finally:
        reopened.close()
