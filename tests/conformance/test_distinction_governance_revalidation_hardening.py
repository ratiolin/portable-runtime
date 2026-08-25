from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from portable_runtime.governance.distinction import (
    APPLY_REVIEW_DISCHARGE,
    DECIDE_REVIEW,
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
    GovernanceProjectionUnavailable,
    RevalidationGovernanceLifecycle,
)
from portable_runtime.records.revalidation import DefaultRevalidationPolicyProfile
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
    backing = SQLiteStateStore(tmp_path / f"hardening-{backend}.db")
    try:
        yield SQLiteDistinctionGovernancePersistence(backing)
    finally:
        backing.close()


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=10,
    )


def _relation(*, relation_type: str, target: str = "d") -> _Relation:
    return _Relation(
        id="rel-1",
        relation_type=relation_type,
        object_ref="model:v2",
        subject_ref=target,
    )


def _lifecycle(
    persistence: DistinctionGovernancePersistence,
    anchors: dict[str, str],
    *grants: AuthorityGrant,
) -> RevalidationGovernanceLifecycle:
    return RevalidationGovernanceLifecycle(
        persistence=persistence,
        authority=grant_authority(grants),
        freshness=anchors.get,
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_rd001_blocking_projection_missing_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        lifecycle = _lifecycle(persistence, {"model:v2": "model:v2@1"})

        with pytest.raises(GovernanceProjectionUnavailable) as exc_info:
            lifecycle.observe_change(
                event_ref="event-missing",
                change_ref="model:v2",
                change_type="model",
                relations=[_relation(relation_type="validated-under", target="unrepresented")],
                context="ctx",
            )

        projection = exc_info.value.projection
        assert projection.status == "projection-unavailable"
        assert projection.action == "block-next-use"
        assert projection.target == "unrepresented"
        assert projection.blocking
        assert projection.obligation is None
        assert persistence.list_obligations() == {}


@pytest.mark.parametrize("backend", BACKENDS)
def test_rd002_nonblocking_projection_missing_is_explicit(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        lifecycle = _lifecycle(persistence, {"model:v2": "model:v2@1"})

        result = lifecycle.observe_change(
            event_ref="event-missing-background",
            change_ref="model:v2",
            change_type="model",
            relations=[_relation(relation_type="depends-on", target="unrepresented")],
            context="ctx",
        )

        assert result.opened_obligations == ()
        assert len(result.projection_unavailable) == 1
        projection = result.projection_unavailable[0]
        assert projection.status == "projection-unavailable"
        assert projection.action == "background-revalidate"
        assert not projection.blocking
        assert persistence.list_obligations() == {}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.xfail(
    strict=True,
    reason="Phase D.5 must deduplicate by durable EventInstanceKey, independent of policy disposition",
)
def test_rd003_same_event_replay_with_policy_change_cannot_open_new_review(
    backend: str,
    tmp_path: Path,
) -> None:
    with _persistence(backend, tmp_path) as persistence:
        state = _state()
        persistence.seed_state("d", state)
        anchors = {"model:v2": "model:v2@1"}
        bootstrap = _lifecycle(persistence, anchors)
        first = bootstrap.observe_change(
            event_ref="stable-event",
            change_ref="model:v2",
            change_type="model",
            relations=[_relation(relation_type="depends-on")],
            context="ctx",
        )
        qid = first.opened_obligations[0].id
        decision = GovernanceDecision(
            id="dec-background",
            actor="reviewer",
            operation=DECIDE_REVIEW,
            target="d",
            context="ctx",
            review_refs=(qid,),
            disposition="no_change",
            expected_state_anchor=state_anchor(state),
            basis_anchors=(("model:v2", "model:v2@1"),),
            scope_snapshot=state.scope,
            partition_snapshot=state.partition,
            closure_facts=frozenset({"basis_checked"}),
        )
        discharge = GovernedApplication(
            id="app-discharge-background",
            actor="closer",
            operation=APPLY_REVIEW_DISCHARGE,
            scheme_id="d",
            target=f"review_obligation:{qid}",
            decision_ref=decision.id,
            context="ctx",
            review_obligation_id=qid,
        )
        lifecycle = _lifecycle(
            persistence,
            anchors,
            AuthorityGrant(
                decision.actor,
                decision.operation,
                decision.target,
                decision.context,
            ),
            AuthorityGrant(
                discharge.actor,
                discharge.operation,
                discharge.target,
                discharge.context,
            ),
        )
        lifecycle.record_decision(decision)
        lifecycle.discharge(discharge)
        assert persistence.get_obligation(qid) is None

        stricter_profile = DefaultRevalidationPolicyProfile(
            profile_id="stricter-revalidation-policy",
            required_action_rules={
                "model": {"depends-on": "block-next-use"},
            },
        )
        replay = lifecycle.observe_change(
            event_ref="stable-event",
            change_ref="model:v2",
            change_type="model",
            relations=[_relation(relation_type="depends-on")],
            context="ctx",
            profile=stricter_profile,
        )

        assert replay.opened_obligations == ()
        assert len(replay.already_processed_obligation_ids) == 1
