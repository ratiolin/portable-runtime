"""Revision actor/resource/effect and supersedes provenance invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portable_runtime.records.authorization import AuthorizationGrant, create_grant_for_approval
from portable_runtime.records.models import Assertion, RevisionRecord
from portable_runtime.records.revision import apply_revision, create_revision, supersede
from portable_runtime.protocol.validation import validate_state_graph
from portable_runtime.stores.memory import InMemoryStateStore


def test_revision_apply_uses_explicit_actor_and_binds_supersedes_relation() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assert_revision_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    new = Assertion(id="assert_revision_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    applied = apply_revision(
        revision,
        store=store,
        authorization_ref=grant.id,
        actor_ref="agent:executor",
        resource_ref=old.id,
    )
    assert applied.metadata["actor_ref"] == "agent:executor"
    relation = supersede(old.id, new.id, store=store, revision=applied)
    state_errors = validate_state_graph(store.export_state())
    assert not any("supersedes relation" in error for error in state_errors)
    assert store.get_relation(relation.id) is not None


def test_revision_apply_rejects_mismatched_actual_actor() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assert_revision_actor_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    new = Assertion(id="assert_revision_actor_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    with pytest.raises(ValueError, match="authorization rejected"):
        apply_revision(revision, store=store, authorization_ref=grant.id, actor_ref="agent:other")


def test_revision_apply_rejects_missing_actual_actor() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assert_revision_missing_actor_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    new = Assertion(id="assert_revision_missing_actor_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    with pytest.raises(ValueError, match="explicit actual actor_ref"):
        apply_revision(revision, store=store, authorization_ref=grant.id, resource_ref=old.id)


def test_revision_apply_rejects_caller_selected_resource_or_effect() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assert_revision_contract_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    new = Assertion(id="assert_revision_contract_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    with pytest.raises(ValueError, match="canonical revision subject_ref"):
        apply_revision(
            revision,
            store=store,
            authorization_ref=grant.id,
            actor_ref="agent:executor",
            resource_ref="unrelated-resource",
        )
    with pytest.raises(ValueError, match="fixed to write-local"):
        apply_revision(
            revision,
            store=store,
            authorization_ref=grant.id,
            actor_ref="agent:executor",
            effect_class="read",
        )


def test_revision_authorization_use_preserves_historical_validity() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assert_revision_historical_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    new = Assertion(id="assert_revision_historical_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    applied = apply_revision(revision, store=store, authorization_ref=grant.id, actor_ref="agent:executor")
    use = store.get_authorization_use(applied.metadata["authorization_use_ref"])
    assert use is not None
    expired = grant.model_copy(
        update={
            "expires_at": use.authorized_at + timedelta(seconds=1),
            "revoked_at": use.authorized_at + timedelta(seconds=1),
        }
    )
    store.save_authorization(expired)
    errors = validate_state_graph(store.export_state())
    assert not any(f"revision {applied.id}" in error and "authorization" in error for error in errors)


def _revision_fixture() -> tuple[InMemoryStateStore, Assertion, Assertion, RevisionRecord]:
    store = InMemoryStateStore()
    old = Assertion(id="revision_immutable_old", statement="old", lifecycle_status="current")
    new = Assertion(id="revision_immutable_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    revision = create_revision(old.id, new.id)
    store.save_record(revision)
    return store, old, new, revision


def _revision_grant(store: InMemoryStateStore, revision: RevisionRecord) -> AuthorizationGrant:
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:executor",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    return grant


def test_persisted_revision_proposal_content_is_immutable() -> None:
    store, old, new, revision = _revision_fixture()
    other = Assertion(id="revision_immutable_other", statement="other", lifecycle_status="draft")
    store.save_record(other)

    changed = revision.model_copy(
        update={
            "produces_ref": other.id,
            "version": revision.version + 1,
        }
    )
    with pytest.raises(ValueError, match="persisted Revision proposal"):
        store.save_record(changed)
    canonical = store.get_record(revision.id)
    assert canonical is not None
    assert canonical.produces_ref == new.id
    assert canonical.revises_ref == old.id


def test_applied_revision_endpoints_and_authority_metadata_are_immutable() -> None:
    store, old, new, revision = _revision_fixture()
    other = Assertion(id="revision_applied_other", statement="other", lifecycle_status="draft")
    store.save_record(other)
    grant = _revision_grant(store, revision)
    applied = apply_revision(
        revision,
        store=store,
        authorization_ref=grant.id,
        actor_ref="agent:executor",
        resource_ref=old.id,
    )

    endpoint_change = applied.model_copy(
        update={
            "revises_ref": other.id,
            "version": applied.version + 1,
        }
    )
    with pytest.raises(ValueError, match="persisted Revision proposal"):
        store.save_record(endpoint_change)

    metadata_change = applied.model_copy(
        update={
            "metadata": {**applied.metadata, "actor_ref": "agent:other"},
            "version": applied.version + 1,
        }
    )
    with pytest.raises(ValueError, match="authority metadata"):
        store.save_record(metadata_change)


def test_apply_revision_is_idempotent_after_grant_revoke() -> None:
    store, old, _new, revision = _revision_fixture()
    grant = _revision_grant(store, revision)
    applied = apply_revision(
        revision,
        store=store,
        authorization_ref=grant.id,
        actor_ref="agent:executor",
        resource_ref=old.id,
    )
    use_ref = applied.metadata["authorization_use_ref"]
    uses_before = store.list_authorization_uses()
    version_before = applied.version

    # Simulate a later revocation in the current authorization state.  The
    # historical AuthorizationUse remains valid at its original action time,
    # while an already-applied replay must not consult the grant again.
    revoked = grant.model_copy(update={"revoked_at": applied.created_at})
    store._records["authorization"][grant.id] = revoked.model_copy(deep=True)

    replay = apply_revision(applied, store=store)
    assert replay.id == applied.id
    assert replay.lifecycle_status == "applied"
    assert replay.version == version_before
    assert replay.metadata["authorization_use_ref"] == use_ref
    assert len(store.list_authorization_uses()) == len(uses_before)
