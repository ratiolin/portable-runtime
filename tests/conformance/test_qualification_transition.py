"""Qualification history/currentness contracts for both state stores."""

from __future__ import annotations

import pytest

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.qualification import AssessmentContext, QualificationResolutionError
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    create_authorization_use,
)
from portable_runtime.records.models import Assertion
from portable_runtime.records.qualification_transition import commit_qualification_transition
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _store(backend: str, tmp_path):
    return InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "qualification-transition.db")


def _authorized_after(store, before: Assertion, status: str) -> Assertion:
    grant = AuthorizationGrant(
        id=f"authz_{before.id}",
        principal_ref="owner",
        grantee_ref="agent",
        allowed_capabilities=["record.write"],
        resource_scope=[before.id],
        effect_ceiling="write-local",
        subject_version_refs=[f"{before.id}:v{before.version}"],
    )
    store.save_authorization(grant)
    request = CanonicalAuthorizationRequest(
        capability="record.write",
        actor_ref="agent",
        resource_ref=before.id,
        subject_version_refs=[f"{before.id}:v{before.version}"],
        effect_class="write-local",
    )
    use = create_authorization_use(grant, request)
    store.save_authorization_use(use)
    return before.model_copy(
        update={
            "epistemic_status": status,
            "version": before.version + 1,
            "metadata": {**before.metadata, "authorization_use_ref": use.id},
        }
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_epistemic_transition_requires_matching_append_only_event(backend: str, tmp_path) -> None:
    store = _store(backend, tmp_path)
    try:
        before = Assertion(
            id="assert_transition_guard",
            statement="current qualification",
            lifecycle_status="current",
            epistemic_status="supported",
            version=1,
        )
        store.save_record(before)
        after = _authorized_after(store, before, "revalidation-required")
        with pytest.raises(ValueError, match="qualification transition"):
            store.save_record(after)
        event = commit_qualification_transition(
            store,
            after,
            expected_version=1,
            reason_refs=["environment:v2"],
            event_id="event_transition_guard",
        )
        assert event.type == "qualification.status.changed"
        assert store.get_record(before.id).epistemic_status == "revalidation-required"
        events = store.list_events(before.id)
        assert [item.id for item in events] == ["event_transition_guard"]
        assert events[0].payload["before"]["epistemic_status"] == "supported"
        assert events[0].payload["after"]["epistemic_status"] == "revalidation-required"
    finally:
        if backend == "sqlite":
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_transition_event_rolls_back_when_semantic_authority_fails(backend: str, tmp_path) -> None:
    store = _store(backend, tmp_path)
    try:
        before = Assertion(
            id="assert_transition_rollback",
            statement="current qualification",
            lifecycle_status="current",
            epistemic_status="supported",
            version=1,
        )
        store.save_record(before)
        unauthorized = before.model_copy(update={"epistemic_status": "contested", "version": 2})
        with pytest.raises(ValueError, match="authority proof"):
            commit_qualification_transition(
                store,
                unauthorized,
                expected_version=1,
                reason_refs=["observation:new"],
                event_id="event_transition_rollback",
            )
        assert store.get_event("event_transition_rollback") is None
        assert store.get_record(before.id).epistemic_status == "supported"
    finally:
        if backend == "sqlite":
            store.close()


def _qualification_request(assertion: Assertion) -> CapabilityRequest:
    return CapabilityRequest(
        id=f"request_{assertion.id}",
        capability="test.read",
        metadata={
            "qualification_refs": [
                {"id": assertion.id, "kind": "assertion", "version": assertion.version}
            ]
        },
    )


def test_positive_assertion_qualification_must_be_current_and_supported() -> None:
    store = InMemoryStateStore()
    supported = Assertion(
        id="assert_current_supported",
        statement="qualified",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    store.save_record(supported)
    assert AssessmentContext.resolve(store, _qualification_request(supported)).refs

    stale = Assertion(
        id="assert_stale_supported",
        statement="stale",
        lifecycle_status="superseded",
        epistemic_status="supported",
        version=1,
    )
    store.save_record(stale)
    with pytest.raises(QualificationResolutionError, match="stale lifecycle"):
        AssessmentContext.resolve(store, _qualification_request(stale))

    revalidation = Assertion(
        id="assert_revalidation_required",
        statement="needs fresh evidence",
        lifecycle_status="current",
        epistemic_status="revalidation-required",
        version=1,
    )
    store.save_record(revalidation)
    with pytest.raises(QualificationResolutionError, match="currently supported"):
        AssessmentContext.resolve(store, _qualification_request(revalidation))


def test_qualification_transition_cannot_bundle_other_semantic_changes() -> None:
    store = InMemoryStateStore()
    before = Assertion(
        id="assert_narrow_transition",
        statement="same proposition",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    store.save_record(before)
    after = _authorized_after(store, before, "contested").model_copy(
        update={"assumptions": ["silently changed"]}
    )
    with pytest.raises(ValueError, match="cannot bundle other semantic changes"):
        commit_qualification_transition(
            store,
            after,
            expected_version=1,
            reason_refs=["observation:new"],
            event_id="event_narrow_transition",
        )
    assert store.get_event("event_narrow_transition") is None
    assert store.get_record(before.id).assumptions == []
