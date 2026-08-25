from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Work
from portable_runtime.governance.adapters import (
    CanonicalFreshnessAdapter,
    CanonicalGovernanceAuthorizationAdapter,
    governance_capability,
)
from portable_runtime.governance.canonical import GOVERNANCE_APPLICATION_COMMITTED
from portable_runtime.governance.distinction import (
    APPLY_QUALIFICATION,
    APPLY_REVIEW_DISCHARGE,
    DECIDE_QUALIFICATION,
    DECIDE_REVIEW,
    AuthorityGrant,
    BlockingCondition,
    DistinctionState,
    GovernanceConfiguration,
    GovernanceDecision,
    GovernanceRuntime,
    GovernedApplication,
    ReviewObligation,
    RuntimeDistinctionProjection,
    UseContext,
    apply_state_transition,
    decision_authority_request,
    grant_authority,
    projection_authority_target,
    qualification_context,
    record_decision,
    state_anchor,
    usable,
)
from portable_runtime.governance.persistence import (
    DistinctionGovernancePersistence,
    GovernancePersistenceError,
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.revalidation import RevalidationGovernanceLifecycle
from portable_runtime.records.authorization import AuthorizationGrant
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
    suffix: str = "source",
) -> Iterator[tuple[Any, DistinctionGovernancePersistence]]:
    if backend == "memory":
        store = InMemoryStateStore()
        yield store, InMemoryDistinctionGovernancePersistence(store)
        return
    store = SQLiteStateStore(tmp_path / f"d5-{backend}-{suffix}.db")
    try:
        yield store, SQLiteDistinctionGovernancePersistence(store)
    finally:
        store.close()


def _state(*, version: int = 10) -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=version,
    )


def _obligation(
    *,
    qid: str = "q-1",
    event_ref: str = "event-1",
    basis_ref: str = "basis-1",
    blocking_condition: BlockingCondition | None = None,
) -> ReviewObligation:
    return ReviewObligation(
        id=qid,
        target="d",
        trigger_ref=event_ref,
        basis_refs=(basis_ref,),
        context="ctx",
        blocking=True,
        blocking_condition=blocking_condition,
        closure_requirements=frozenset({"basis_checked"}),
    )


def _no_change_decision(
    state: DistinctionState,
    *,
    qid: str,
    basis_ref: str,
    basis_anchor: str,
    decision_id: str = "dec-review",
) -> GovernanceDecision:
    return GovernanceDecision(
        id=decision_id,
        actor="reviewer",
        operation=DECIDE_REVIEW,
        target="d",
        context="ctx",
        review_refs=(qid,),
        disposition="no_change",
        expected_state_anchor=state_anchor(state),
        basis_anchors=((basis_ref, basis_anchor),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
    )


def _transition_decision(
    state: DistinctionState,
    *,
    qid: str,
    basis_ref: str,
    basis_anchor: str,
) -> GovernanceDecision:
    return GovernanceDecision(
        id="dec-transition",
        actor="reviewer",
        operation=DECIDE_QUALIFICATION,
        target="d",
        context="ctx",
        review_refs=(qid,),
        disposition="transition_required",
        expected_state_anchor=state_anchor(state),
        basis_anchors=((basis_ref, basis_anchor),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
        required_qualification="qualified",
        required_activation="suspended",
    )


def _discharge(decision: GovernanceDecision, qid: str) -> GovernedApplication:
    return GovernedApplication(
        id="app-discharge",
        actor="closer",
        operation=APPLY_REVIEW_DISCHARGE,
        scheme_id="d",
        target=f"review_obligation:{qid}",
        decision_ref=decision.id,
        context="ctx",
        review_obligation_id=qid,
    )


def _state_application(decision: GovernanceDecision) -> GovernedApplication:
    return GovernedApplication(
        id="app-state",
        actor="operator",
        operation=APPLY_QUALIFICATION,
        scheme_id="d",
        target="d",
        decision_ref=decision.id,
        context="ctx",
        new_qualification=decision.required_qualification,
        new_activation=decision.required_activation,
    )


def _clear_sidecar(backend: str, store: Any) -> None:
    if backend == "memory":
        records = vars(store)["_distinction_governance_records"]
        for values in records.values():
            values.clear()
        return
    connection = vars(store)["_connection"]
    connection.execute("DELETE FROM runtime_governance_records")


def test_d5_001_runtime_projection_name_keeps_version_outside_semantic_axes() -> None:
    first = _state(version=10)
    second = replace(first, version=11)

    assert RuntimeDistinctionProjection is DistinctionState
    assert qualification_context(first) == qualification_context(second)
    assert first.operational_anchor != second.operational_anchor


def test_d5_002_structured_authority_distinguishes_projection_scope() -> None:
    state = _state()
    obligation = _obligation()
    config = GovernanceConfiguration(
        states={"d": state},
        runtime=GovernanceRuntime(obligations={obligation.id: obligation}),
    )
    decision = _no_change_decision(
        state,
        qid=obligation.id,
        basis_ref="basis-1",
        basis_anchor="basis@1",
    )
    exact = AuthorityGrant(
        actor=decision.actor,
        operation=decision.operation,
        target=projection_authority_target(
            "d",
            state.scope,
            state.partition,
            state_anchor(state),
        ),
        context="ctx",
    )
    narrower = AuthorityGrant(
        actor=decision.actor,
        operation=decision.operation,
        target=projection_authority_target(
            "d",
            frozenset({"a"}),
            (frozenset({"a"}),),
            state_anchor(state),
        ),
        context="ctx",
    )

    assert record_decision(config, decision, grant_authority([exact])) is not None
    assert record_decision(config, decision, grant_authority([narrower])) is None


def test_d5_003_scope_match_and_serializable_blocking_condition() -> None:
    state = _state()
    obligation = _obligation(
        blocking_condition=BlockingCondition(
            context_names=frozenset({"ctx"}),
            scope_any=frozenset({"a"}),
        )
    )
    config = GovernanceConfiguration(
        states={"d": state},
        runtime=GovernanceRuntime(obligations={obligation.id: obligation}),
    )

    assert not usable(config, "d", UseContext("ctx", frozenset({"a"})))
    assert usable(config, "d", UseContext("ctx", frozenset({"b"})))
    assert not usable(config, "d", UseContext("ctx", frozenset({"c"})))
    assert usable(config, "d", UseContext("other", frozenset({"a"})))


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_004_existing_authorization_adapter_binds_projection_anchor(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path) as (store, _persistence):
        state = _state()
        decision = GovernanceDecision(
            id="dec-auth",
            actor="reviewer",
            operation=DECIDE_REVIEW,
            target="d",
            context="ctx",
            review_refs=("q-1",),
            disposition="no_change",
            expected_state_anchor=state_anchor(state),
            basis_anchors=(("basis-1", "basis@1"),),
            scope_snapshot=state.scope,
            partition_snapshot=state.partition,
        )
        grant = AuthorizationGrant(
            id="auth-governance",
            principal_ref="owner",
            grantee_ref="reviewer",
            allowed_capabilities=[governance_capability(DECIDE_REVIEW)],
            resource_scope=["distinction:d"],
            effect_ceiling="read",
            subject_version_refs=[state_anchor(state)],
        )
        store.save_authorization(grant)
        adapter = CanonicalGovernanceAuthorizationAdapter(store)
        request = decision_authority_request(decision)

        assert adapter(request)
        use = adapter.materialize_use(request)
        assert store.get_authorization_use(use.id) == use

        changed = replace(state, version=state.version + 1)
        stale_request = decision_authority_request(
            replace(
                decision,
                expected_state_anchor=state_anchor(changed),
            )
        )
        assert not adapter(stale_request)


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_005_existing_freshness_adapter_tracks_canonical_record_content(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path) as (store, _persistence):
        first = Work(id="basis-work", title="basis", description="v1")
        store.save_work(first)
        freshness = CanonicalFreshnessAdapter(store)
        first_anchor = freshness("basis-work")
        assert first_anchor is not None

        store.save_work(first.model_copy(update={"description": "v2"}))
        second_anchor = freshness("basis-work")

        assert second_anchor is not None
        assert second_anchor != first_anchor


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_006_sidecar_can_be_deleted_and_rebuilt_from_canonical_history(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path) as (store, persistence):
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        lifecycle = RevalidationGovernanceLifecycle(
            persistence=persistence,
            authority=grant_authority([]),
            freshness=anchors.get,
        )
        result = lifecycle.observe_change(
            event_ref="event-rebuild",
            change_ref="model:v2",
            change_type="model",
            relations=[_Relation("rel-1", "validated-under", "model:v2", "d")],
            context="ctx",
        )
        qid = result.opened_obligations[0].id
        decision = _no_change_decision(
            state,
            qid=qid,
            basis_ref="model:v2",
            basis_anchor="model:v2@1",
        )
        discharge = _discharge(decision, qid)
        lifecycle = RevalidationGovernanceLifecycle(
            persistence=persistence,
            authority=grant_authority(
                [
                    AuthorityGrant(decision.actor, decision.operation, "d", "ctx"),
                    AuthorityGrant(discharge.actor, discharge.operation, discharge.target, "ctx"),
                ]
            ),
            freshness=anchors.get,
        )
        lifecycle.record_decision(decision)
        lifecycle.discharge(discharge)
        expected = lifecycle.snapshot()
        assert any(event.type.startswith("governance.distinction.") for event in store.list_events())

        _clear_sidecar(backend, store)
        assert persistence.list_states() == {}
        assert persistence.list_decisions() == {}
        assert persistence.list_applications() == {}

        rebuilt = persistence.rebuild_projection_from_canonical_history()
        assert rebuilt == expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_007_export_import_rebuilds_equivalent_governance_configuration(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="export") as (source, persistence):
        state = _state()
        persistence.seed_state("d", state)
        lifecycle = RevalidationGovernanceLifecycle(
            persistence=persistence,
            authority=grant_authority([]),
            freshness={"model:v2": "model:v2@1"}.get,
        )
        lifecycle.observe_change(
            event_ref="event-portable",
            change_ref="model:v2",
            change_type="model",
            relations=[_Relation("rel-1", "validated-under", "model:v2", "d")],
            context="ctx",
        )
        expected = lifecycle.snapshot()
        exported = source.export_state()

    with _backend(backend, tmp_path, suffix="import") as (target, target_persistence):
        target.import_state(exported)
        assert target_persistence.list_states() == {}
        assert target_persistence.list_obligations() == {}

        rebuilt = target_persistence.rebuild_projection_from_canonical_history()
        assert rebuilt == expected
        assert target_persistence.processed_event_obligation_ids("event-portable") is not None


class _ChangingFreshness:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, _basis_ref: str) -> str:
        self.calls += 1
        return "basis@1" if self.calls == 1 else "basis@2"


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_008_commit_boundary_rechecks_freshness_and_rolls_back(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path) as (store, persistence):
        state = _state()
        obligation = _obligation()
        persistence.seed_state("d", state)
        persistence.open_obligation(obligation)
        decision = _transition_decision(
            state,
            qid=obligation.id,
            basis_ref="basis-1",
            basis_anchor="basis@1",
        )
        persistence.record_decision(decision)
        application = _state_application(decision)
        freshness = _ChangingFreshness()
        lifecycle = RevalidationGovernanceLifecycle(
            persistence=persistence,
            authority=grant_authority(
                [AuthorityGrant(application.actor, application.operation, "d", "ctx")]
            ),
            freshness=freshness,
        )

        with pytest.raises(GovernancePersistenceError, match="basis changed"):
            lifecycle.apply_state(application)

        assert freshness.calls >= 2
        assert persistence.get_state("d") == state
        assert persistence.get_application(application.id) is None
        assert not any(
            event.type == GOVERNANCE_APPLICATION_COMMITTED
            and event.subject_ref == "d"
            for event in store.list_events()
        )


@pytest.mark.parametrize("backend", BACKENDS)
def test_d5_009_canonical_event_failure_rolls_back_projection_and_application(
    backend: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _backend(backend, tmp_path) as (store, persistence):
        state = _state()
        obligation = _obligation()
        persistence.seed_state("d", state)
        persistence.open_obligation(obligation)
        decision = _transition_decision(
            state,
            qid=obligation.id,
            basis_ref="basis-1",
            basis_anchor="basis@1",
        )
        persistence.record_decision(decision)
        application = _state_application(decision)
        admitted = apply_state_transition(
            persistence._configuration(),
            application,
            grant_authority([AuthorityGrant(application.actor, application.operation, "d", "ctx")]),
            {"basis-1": "basis@1"}.get,
        )
        assert admitted is not None
        receipt = admitted.runtime.applications[application.id]
        next_state = admitted.states["d"]
        original_append = store.append_event

        def fail_application_event(event: Any) -> None:
            if event.type == GOVERNANCE_APPLICATION_COMMITTED:
                raise RuntimeError("injected canonical event failure")
            original_append(event)

        monkeypatch.setattr(store, "append_event", fail_application_event)
        with pytest.raises(RuntimeError, match="injected canonical event failure"):
            persistence.commit_state_application(
                "d",
                next_state,
                receipt,
                freshness={"basis-1": "basis@1"}.get,
            )

        assert persistence.get_state("d") == state
        assert persistence.get_application(application.id) is None


def test_d5_010_policy_output_does_not_create_authority() -> None:
    store = InMemoryStateStore()
    adapter = CanonicalGovernanceAuthorizationAdapter(store)
    state = _state()
    decision = GovernanceDecision(
        id="dec-policy-is-not-authority",
        actor="reviewer",
        operation=DECIDE_REVIEW,
        target="d",
        context="ctx",
        review_refs=("q-1",),
        disposition="no_change",
        expected_state_anchor=state_anchor(state),
        basis_anchors=(("basis-1", "basis@1"),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
    )

    assert not adapter(decision_authority_request(decision))
