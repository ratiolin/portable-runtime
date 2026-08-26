"""B4-P3a conformance for authoritative RecoveryDisposition preparation."""

from __future__ import annotations

from typing import Any

import pytest

from portable_runtime.records.models import OutcomeRecord
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.recovery_disposition import (
    RecoveryDispositionCommitRequest,
    prepare_recovery_disposition,
    reconstruct_recovery_disposition_basis,
    recovery_disposition_from_event,
)
from tests.conformance.test_recovery_disposition_counterexamples import (
    _Policy,
    _confirm,
    _observe,
    _seed_subject,
)


def _request(
    graph: dict[str, Any],
    *,
    observation_refs: tuple[str, ...],
    outcome_refs: tuple[str, ...] = (),
) -> RecoveryDispositionCommitRequest:
    return RecoveryDispositionCommitRequest(
        dispatch_commit_ref=str(graph["dispatch_ref"]),
        observation_refs=observation_refs,
        outcome_refs=outcome_refs,
        policy_ref="policy:recovery:v1",
    )


def test_p3a_reconstructs_canonical_store_derived_basis() -> None:
    store = InMemoryStateStore()
    graph = _seed_subject(store, "p3a-basis")
    obs_a = _observe(store, graph, instance_ref="obs:p3a:a")
    obs_b = _observe(store, graph, instance_ref="obs:p3a:b")
    out_a = _confirm(store, graph, proof_id="proof:p3a:a")
    out_b = _confirm(store, graph, proof_id="proof:p3a:b")

    first = reconstruct_recovery_disposition_basis(
        store,
        _request(
            graph,
            observation_refs=(obs_b.id, obs_a.id, obs_b.id),
            outcome_refs=(out_b.id, out_a.id, out_b.id),
        ),
    )
    reordered = reconstruct_recovery_disposition_basis(
        store,
        _request(
            graph,
            observation_refs=(obs_a.id, obs_b.id),
            outcome_refs=(out_a.id, out_b.id),
        ),
    )

    assert first == reordered
    assert first.observation_refs == tuple(sorted({obs_a.id, obs_b.id}))
    assert first.outcome_refs == tuple(sorted({out_a.id, out_b.id}))
    assert first.recovery_mode == "reconcile"
    assert first.effect_semantics == "reconcilable"
    assert first.reversibility == "unknown"
    assert first.action_ref == graph["action"].id
    assert first.attempt_ref == graph["attempt"].id
    assert first.step_ref == graph["step"].id


def test_p3a_rejects_observation_from_other_dispatch_graph() -> None:
    store = InMemoryStateStore()
    first = _seed_subject(store, "p3a-obs-first")
    second = _seed_subject(store, "p3a-obs-second")
    foreign = _observe(store, second, instance_ref="obs:p3a:foreign")

    with pytest.raises(ValueError, match="RecoveryObservation|dispatch"):
        reconstruct_recovery_disposition_basis(
            store,
            _request(first, observation_refs=(foreign.id,)),
        )


def test_p3a_rejects_confirmed_outcome_from_other_action() -> None:
    store = InMemoryStateStore()
    first = _seed_subject(store, "p3a-out-first")
    second = _seed_subject(store, "p3a-out-second")
    obs = _observe(store, first, instance_ref="obs:p3a:first")
    foreign = _confirm(store, second, proof_id="proof:p3a:foreign")

    with pytest.raises(ValueError, match="Outcome.*Action|binding"):
        reconstruct_recovery_disposition_basis(
            store,
            _request(
                first,
                observation_refs=(obs.id,),
                outcome_refs=(foreign.id,),
            ),
        )


def test_p3a_rejects_unconfirmed_outcome_even_for_same_action() -> None:
    store = InMemoryStateStore()
    graph = _seed_subject(store, "p3a-unconfirmed")
    obs = _observe(store, graph, instance_ref="obs:p3a:unconfirmed")
    outcome = OutcomeRecord(
        id="outcome:p3a:unconfirmed",
        action_ref=graph["action"].id,
        lifecycle_status="recorded",
    )
    store.save_record(outcome)

    with pytest.raises(ValueError, match="confirmed"):
        reconstruct_recovery_disposition_basis(
            store,
            _request(
                graph,
                observation_refs=(obs.id,),
                outcome_refs=(outcome.id,),
            ),
        )


def test_p3a_policy_output_is_semantics_not_identity() -> None:
    store = InMemoryStateStore()
    graph = _seed_subject(store, "p3a-policy")
    obs = _observe(store, graph, instance_ref="obs:p3a:policy")
    basis = reconstruct_recovery_disposition_basis(
        store,
        _request(graph, observation_refs=(obs.id,)),
    )

    hold = prepare_recovery_disposition(basis, _Policy("hold-unresolved"))
    retry = prepare_recovery_disposition(basis, _Policy("retry-idempotent"))

    assert hold.disposition.id == retry.disposition.id
    assert hold.disposition.basis_key == retry.disposition.basis_key
    assert hold.disposition.action != retry.disposition.action


def test_p3a_prepared_event_round_trips_exact_semantics() -> None:
    store = InMemoryStateStore()
    graph = _seed_subject(store, "p3a-roundtrip")
    obs = _observe(store, graph, instance_ref="obs:p3a:roundtrip")
    basis = reconstruct_recovery_disposition_basis(
        store,
        _request(graph, observation_refs=(obs.id,)),
    )
    policy = _Policy("hold-unresolved")

    prepared = prepare_recovery_disposition(basis, policy)

    assert policy.calls == 1
    assert recovery_disposition_from_event(prepared.event) == prepared.disposition
    assert prepared.event.id == prepared.disposition.id
    assert prepared.event.subject_ref == graph["dispatch_ref"]


def test_p3a_rejects_policy_action_outside_frozen_vocabulary() -> None:
    store = InMemoryStateStore()
    graph = _seed_subject(store, "p3a-policy-invalid")
    obs = _observe(store, graph, instance_ref="obs:p3a:policy-invalid")
    basis = reconstruct_recovery_disposition_basis(
        store,
        _request(graph, observation_refs=(obs.id,)),
    )

    with pytest.raises(ValueError, match="unsupported action"):
        prepare_recovery_disposition(basis, _Policy("execute-now"))
