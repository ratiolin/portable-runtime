"""Revision actor/resource/effect and supersedes provenance invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.models import Assertion
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
    expired = grant.model_copy(update={"expires_at": grant.valid_from + timedelta(seconds=1)})
    store.save_authorization(expired)
    errors = validate_state_graph(store.export_state())
    assert not any(f"revision {applied.id}" in error and "authorization" in error for error in errors)
