from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from portable_runtime.governance.distinction import (
    APPLY_QUALIFICATION,
    APPLY_REVIEW_DISCHARGE,
    DECIDE_QUALIFICATION,
    DECIDE_REVIEW,
    ApplicationReceipt,
    AuthorityGrant,
    DistinctionState,
    GovernanceDecision,
    GovernedApplication,
    grant_authority,
    state_anchor,
)
from portable_runtime.governance.persistence import (
    DistinctionGovernancePersistence,
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.revalidation import (
    GovernanceLifecycleRejected,
    RevalidationGovernanceLifecycle,
)
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
def _persistence(
    backend: str,
    tmp_path: Path,
) -> Iterator[DistinctionGovernancePersistence]:
    if backend == "memory":
        backing = InMemoryStateStore()
        yield InMemoryDistinctionGovernancePersistence(backing)
        return
    backing = SQLiteStateStore(tmp_path / f"{backend}.db")
    try:
        yield SQLiteDistinctionGovernancePersistence(backing)
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


def _relation(
    *,
    change_ref: str = "model:v2",
    target: str = "d",
    relation_type: str = "validated-under",
    relation_id: str = "rel-1",
) -> _Relation:
    return _Relation(
        id=relation_id,
        relation_type=relation_type,
        object_ref=change_ref,
        subject_ref=target,
    )


def _authority(*grants: AuthorityGrant):
    return grant_authority(grants)


def _lifecycle(
    persistence: DistinctionGovernancePersistence,
    anchors: dict[str, str],
    *grants: AuthorityGrant,
) -> RevalidationGovernanceLifecycle:
    return RevalidationGovernanceLifecycle(
        persistence=persistence,
        authority=_authority(*grants),
        freshness=anchors.get,
    )


def _open_model_review(
    lifecycle: RevalidationGovernanceLifecycle,
    *,
    event_ref: str = "event-1",
    change_ref: str = "model:v2",
    relation_type: str = "validated-under",
):
    return lifecycle.observe_change(
        event_ref=event_ref,
        change_ref=change_ref,
        change_type="model",
        relations=[
            _relation(
                change_ref=change_ref,
                relation_type=relation_type,
            )
        ],
        context="ctx",
    )


def _no_change_decision(
    state: DistinctionState,
    *,
    qid: str,
    change_ref: str = "model:v2",
    anchor: str = "model:v2@1",
    decision_id: str = "dec-review",
    closure_facts: frozenset[str] = frozenset({"basis_checked"}),
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
        basis_anchors=((change_ref, anchor),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=closure_facts,
    )


def _transition_decision(
    state: DistinctionState,
    *,
    qid: str,
    change_ref: str = "model:v2",
    anchor: str = "model:v2@1",
    decision_id: str = "dec-transition",
) -> GovernanceDecision:
    return GovernanceDecision(
        id=decision_id,
        actor="reviewer",
        operation=DECIDE_QUALIFICATION,
        target="d",
        context="ctx",
        review_refs=(qid,),
        disposition="transition_required",
        expected_state_anchor=state_anchor(state),
        basis_anchors=((change_ref, anchor),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
        required_qualification="qualified",
        required_activation="suspended",
    )


def _state_application(
    decision: GovernanceDecision,
    *,
    app_id: str = "app-state",
) -> GovernedApplication:
    return GovernedApplication(
        id=app_id,
        actor="operator",
        operation=APPLY_QUALIFICATION,
        scheme_id="d",
        target="d",
        decision_ref=decision.id,
        context="ctx",
        new_qualification=decision.required_qualification,
        new_activation=decision.required_activation,
    )


def _discharge_application(
    decision: GovernanceDecision,
    *,
    qid: str,
    app_id: str = "app-discharge",
) -> GovernedApplication:
    return GovernedApplication(
        id=app_id,
        actor="closer",
        operation=APPLY_REVIEW_DISCHARGE,
        scheme_id="d",
        target=f"review_obligation:{qid}",
        decision_ref=decision.id,
        context="ctx",
        review_obligation_id=qid,
    )


def _decision_grant(decision: GovernanceDecision) -> AuthorityGrant:
    return AuthorityGrant(
        decision.actor,
        decision.operation,
        decision.target,
        decision.context,
    )


def _application_grant(application: GovernedApplication) -> AuthorityGrant:
    return AuthorityGrant(
        application.actor,
        application.operation,
        application.target,
        application.context,
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_r001_warn_impact_does_not_invalidate_or_open_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        lifecycle = _lifecycle(persistence, {"env:v2": "env:v2@1"})

        result = lifecycle.observe_change(
            event_ref="event-warn",
            change_ref="env:v2",
            change_type="environment",
            relations=[
                _relation(
                    change_ref="env:v2",
                    relation_type="depends-on",
                )
            ],
            context="ctx",
        )

        assert len(result.assessments) == 1
        assert result.assessments[0].revalidation_disposition is not None
        assert result.assessments[0].revalidation_disposition.action == "warn"
        assert result.opened_obligations == ()
        assert persistence.get_state("d") == state
        assert lifecycle.is_usable("d", "ctx")


@pytest.mark.parametrize("backend", BACKENDS)
def test_r002_background_revalidation_opens_nonblocking_review_only(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        lifecycle = _lifecycle(persistence, {"model:v2": "model:v2@1"})

        result = _open_model_review(
            lifecycle,
            event_ref="event-background",
            relation_type="depends-on",
        )

        assert len(result.opened_obligations) == 1
        obligation = result.opened_obligations[0]
        assert not obligation.blocking
        assert persistence.get_state("d") == state
        assert lifecycle.is_usable("d", "ctx")


@pytest.mark.parametrize("backend", BACKENDS)
def test_r003_block_next_use_opens_blocking_review_without_disqualifying_state(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        lifecycle = _lifecycle(persistence, {"model:v2": "model:v2@1"})

        result = _open_model_review(lifecycle)

        assert len(result.opened_obligations) == 1
        obligation = result.opened_obligations[0]
        assert obligation.blocking
        assert persistence.get_state("d") == state
        assert persistence.get_state("d").qualification == "qualified"  # type: ignore[union-attr]
        assert persistence.get_state("d").activation == "active"  # type: ignore[union-attr]
        assert not lifecycle.is_usable("d", "ctx")


@pytest.mark.parametrize("backend", BACKENDS)
def test_r004_recorded_decision_does_not_change_state_or_close_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        opened = _open_model_review(bootstrap)
        qid = opened.opened_obligations[0].id
        decision = _no_change_decision(state, qid=qid)
        lifecycle = _lifecycle(persistence, anchors, _decision_grant(decision))

        lifecycle.record_decision(decision)

        assert persistence.get_decision(decision.id) == decision
        assert persistence.get_state("d") == state
        assert persistence.get_obligation(qid) is not None
        assert not lifecycle.is_usable("d", "ctx")


@pytest.mark.parametrize("backend", BACKENDS)
def test_r005_state_application_does_not_close_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        opened = _open_model_review(bootstrap)
        qid = opened.opened_obligations[0].id
        decision = _transition_decision(state, qid=qid)
        application = _state_application(decision)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(application),
        )
        lifecycle.record_decision(decision)

        receipt = lifecycle.apply_state(application)

        assert isinstance(receipt, ApplicationReceipt)
        assert persistence.get_state("d") is not None
        assert persistence.get_state("d").activation == "suspended"  # type: ignore[union-attr]
        assert persistence.get_obligation(qid) is not None
        assert not lifecycle.is_usable("d", "ctx")


@pytest.mark.parametrize("backend", BACKENDS)
def test_r006_discharge_rechecks_freshness_and_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        opened = _open_model_review(bootstrap)
        qid = opened.opened_obligations[0].id
        decision = _no_change_decision(state, qid=qid)
        discharge = _discharge_application(decision, qid=qid)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)

        anchors["model:v2"] = "model:v2@2"

        with pytest.raises(GovernanceLifecycleRejected, match="discharge"):
            lifecycle.discharge(discharge)
        assert persistence.get_obligation(qid) is not None
        assert persistence.get_application(discharge.id) is None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r007_same_event_replay_after_discharge_does_not_reopen_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        opened = _open_model_review(bootstrap, event_ref="stable-event")
        qid = opened.opened_obligations[0].id
        decision = _no_change_decision(state, qid=qid)
        discharge = _discharge_application(decision, qid=qid)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)
        lifecycle.discharge(discharge)
        assert persistence.get_obligation(qid) is None

        replay = _open_model_review(lifecycle, event_ref="stable-event")

        assert replay.opened_obligations == ()
        assert replay.already_processed_obligation_ids == (qid,)
        assert persistence.get_obligation(qid) is None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r008_new_event_identity_with_same_content_opens_new_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        first = _open_model_review(bootstrap, event_ref="event-1")
        qid = first.opened_obligations[0].id
        decision = _no_change_decision(state, qid=qid)
        discharge = _discharge_application(decision, qid=qid)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)
        lifecycle.discharge(discharge)

        second = _open_model_review(lifecycle, event_ref="event-2")

        assert len(second.opened_obligations) == 1
        assert second.opened_obligations[0].id != qid
        assert persistence.get_obligation(second.opened_obligations[0].id) is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r009_new_material_review_invalidates_existing_decision(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {
            "model:v2": "model:v2@1",
            "model:v3": "model:v3@1",
        }
        bootstrap = _lifecycle(persistence, anchors)
        first = _open_model_review(bootstrap, event_ref="event-1", change_ref="model:v2")
        qid = first.opened_obligations[0].id
        decision = _no_change_decision(state, qid=qid)
        discharge = _discharge_application(decision, qid=qid)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)

        second = _open_model_review(
            lifecycle,
            event_ref="event-2",
            change_ref="model:v3",
        )
        assert len(second.opened_obligations) == 1
        assert decision.id in second.opened_obligations[0].invalidates_decisions

        with pytest.raises(GovernanceLifecycleRejected, match="discharge"):
            lifecycle.discharge(discharge)
        assert persistence.get_obligation(qid) is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r010_human_review_requirement_cannot_be_silently_omitted(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"permission:v2": "permission:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        result = bootstrap.observe_change(
            event_ref="event-human",
            change_ref="permission:v2",
            change_type="permission",
            relations=[
                _relation(
                    change_ref="permission:v2",
                    relation_type="authorized-under",
                )
            ],
            context="ctx",
        )
        obligation = result.opened_obligations[0]
        assert obligation.blocking
        assert "human_reviewed" in obligation.closure_requirements
        decision = _no_change_decision(
            state,
            qid=obligation.id,
            change_ref="permission:v2",
            anchor="permission:v2@1",
            closure_facts=frozenset({"basis_checked"}),
        )
        discharge = _discharge_application(decision, qid=obligation.id)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)

        with pytest.raises(GovernanceLifecycleRejected, match="discharge"):
            lifecycle.discharge(discharge)
        assert persistence.get_obligation(obligation.id) is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r011_endpoint_match_does_not_substitute_for_matching_application_provenance(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {
            "model:v2": "model:v2@1",
            "model:v3": "model:v3@1",
        }
        bootstrap = _lifecycle(persistence, anchors)
        first = _open_model_review(bootstrap, event_ref="event-a", change_ref="model:v2")
        second = _open_model_review(bootstrap, event_ref="event-b", change_ref="model:v3")
        qa = first.opened_obligations[0].id
        qb = second.opened_obligations[0].id
        dec_a = _transition_decision(
            state,
            qid=qa,
            change_ref="model:v2",
            decision_id="dec-a",
        )
        dec_b = _transition_decision(
            state,
            qid=qb,
            change_ref="model:v3",
            anchor="model:v3@1",
            decision_id="dec-b",
        )
        app_b = _state_application(dec_b, app_id="app-b")
        discharge_a = _discharge_application(dec_a, qid=qa, app_id="discharge-a")
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(dec_a),
            _decision_grant(dec_b),
            _application_grant(app_b),
            _application_grant(discharge_a),
        )
        lifecycle.record_decision(dec_a)
        lifecycle.record_decision(dec_b)
        lifecycle.apply_state(app_b)

        with pytest.raises(GovernanceLifecycleRejected, match="discharge"):
            lifecycle.discharge(discharge_a, state_application=app_b)
        assert persistence.get_obligation(qa) is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_r012_state_transition_then_explicit_discharge_closes_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        opened = _open_model_review(bootstrap)
        qid = opened.opened_obligations[0].id
        decision = _transition_decision(state, qid=qid)
        state_application = _state_application(decision)
        discharge = _discharge_application(decision, qid=qid)
        lifecycle = _lifecycle(
            persistence,
            anchors,
            _decision_grant(decision),
            _application_grant(state_application),
            _application_grant(discharge),
        )
        lifecycle.record_decision(decision)
        lifecycle.apply_state(state_application)
        assert persistence.get_obligation(qid) is not None

        lifecycle.discharge(discharge, state_application=state_application)

        assert persistence.get_obligation(qid) is None
        assert persistence.get_application(discharge.id) is not None
