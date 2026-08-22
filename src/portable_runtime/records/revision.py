"""Revision / Version Lineage — R1.3 implementation milestone.

Preserves old objects and never silently overwrites an authoritative version.

Implements:
  Revision(revises -> old, produces -> new)
  new supersedes -> old

Old objects are retained; supersede mutates lifecycle_status to superseded.
Provides create_revision, apply_revision, supersede.
"""

from __future__ import annotations

from contextlib import nullcontext as _nullcontext
from datetime import UTC, datetime
from typing import Any, Literal, cast

from portable_runtime.core.models import new_id
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    EffectClass,
    is_authorized_for,
    validate_grant,
)
from portable_runtime.records.lifecycle import validate_lifecycle_transition
from portable_runtime.records.models import RevisionRecord
from portable_runtime.records.relations import RecordRelation


def _norm_ref(ref: Any) -> str:
    if isinstance(ref, str):
        return ref
    rid = getattr(ref, "id", None)
    if isinstance(rid, str):
        return rid
    return str(ref)


def create_revision(
    revises_ref: str | Any,
    produces_ref: str | Any,
    *,
    subject_ref: str | Any | None = None,
    created_by: str = "system",
    metadata: dict[str, Any] | None = None,
    lifecycle_status: str = "proposed",
) -> RevisionRecord:
    """Create a Revision linking old -> new."""
    old_id = _norm_ref(revises_ref)
    new_id_str = _norm_ref(produces_ref)
    subj = _norm_ref(subject_ref) if subject_ref is not None else old_id
    if not old_id or not new_id_str:
        raise ValueError("revises_ref and produces_ref must be non-empty")
    if old_id == new_id_str:
        raise ValueError("revises_ref and produces_ref must differ (no self-revision)")
    rec = RevisionRecord(
        id=new_id("revision"),
        subject_ref=subj,
        revises_ref=old_id,
        produces_ref=new_id_str,
        supersedes_ref=old_id,
        created_by=created_by,
        created_at=datetime.now(UTC),
        lifecycle_status=lifecycle_status,  # type: ignore[arg-type]
        version=1,
        metadata=metadata or {},
    )
    return rec


def apply_revision(
    revision: RevisionRecord,
    store: Any | None = None,
    *,
    authorization_ref: str | AuthorizationGrant | None = None,
    actor_ref: str | None = None,
    resource_ref: str | None = None,
    effect_class: str = "write-local",
    legacy_profile: Literal["grant-grantee-compat"] | None = None,
) -> RevisionRecord:
    """Advance a revision toward ``applied`` with an explicit grant proof.

    Revision lifecycle helpers do not manufacture authorization.  A durable
    grant must already exist in ``store`` and bind this revision id/version.
    """
    input_revision = revision
    if store is None or not hasattr(store, "get_authorization"):
        raise ValueError("apply_revision requires a state store and authorization_ref")
    stored_revision = store.get_record(revision.id) if hasattr(store, "get_record") else None
    if stored_revision is None and revision.lifecycle_status == "proposed":
        old_endpoint = store.get_record(revision.revises_ref) if revision.revises_ref else None
        new_endpoint = store.get_record(revision.produces_ref) if revision.produces_ref else None
        if old_endpoint is None or new_endpoint is None or old_endpoint.record_type != new_endpoint.record_type:
            raise ValueError("apply_revision requires canonical revision endpoints")
        # A proposal may be materialized once, but authorization is still
        # checked below through the canonical typed request before it can take
        # effect.
        store.save_record(revision)
        stored_revision = store.get_record(revision.id)
    if not isinstance(stored_revision, RevisionRecord):
        raise ValueError("apply_revision requires the canonical persisted Revision")
    if any(
        getattr(stored_revision, field, None) != getattr(revision, field, None)
        for field in ("version", "subject_ref", "revises_ref", "produces_ref", "supersedes_ref")
    ):
        raise ValueError("apply_revision revision endpoints/version do not match canonical state")
    grant_ref = authorization_ref
    grant_id = grant_ref.id if isinstance(grant_ref, AuthorizationGrant) else grant_ref if isinstance(grant_ref, str) else None
    grant = store.get_authorization(grant_id) if isinstance(grant_id, str) and grant_id else None
    if not isinstance(grant, AuthorizationGrant):
        raise ValueError("apply_revision requires an existing AuthorizationGrant")
    grant_errors = validate_grant(grant)
    expected_versions = [revision.id, f"{revision.id}:v{revision.version}"]
    metadata = stored_revision.metadata if isinstance(stored_revision.metadata, dict) else {}
    # New/canonical callers must provide the actor that actually performed the
    # apply.  A grant is evidence of authorization, never the source of actor
    # identity.  A legacy migration may opt into the compatibility profile
    # explicitly; that profile is never selected implicitly on the canonical
    # path and is marked in persisted metadata.
    actual_actor = actor_ref or metadata.get("actor_ref")
    legacy_actor = False
    if not isinstance(actual_actor, str) or not actual_actor.strip():
        if legacy_profile != "grant-grantee-compat":
            raise ValueError("apply_revision requires explicit actual actor_ref")
        actual_actor = grant.grantee_ref
        legacy_actor = True
    actual_resource = resource_ref or metadata.get("resource_ref") or stored_revision.subject_ref
    if not isinstance(actual_resource, str) or not actual_resource.strip():
        raise ValueError("apply_revision requires a non-empty resource_ref")
    request = CanonicalAuthorizationRequest(
        capability="revision.apply",
        actor_ref=actual_actor,
        resource_ref=actual_resource,
        subject_version_refs=expected_versions,
        effect_class=cast(EffectClass, effect_class),
    )
    if grant_errors or not is_authorized_for(request, grant) or not set(expected_versions).intersection(grant.subject_version_refs):
        detail = "; ".join(grant_errors) if grant_errors else "grant does not bind this revision version"
        raise ValueError(f"revision authorization rejected: {detail}")
    revision_metadata = {
        **stored_revision.metadata,
        "authorization_ref": grant_id,
        "actor_ref": actual_actor,
        "resource_ref": actual_resource,
        "effect_class": effect_class,
    }
    if legacy_actor:
        revision_metadata["legacy_actor_identity"] = "grant-grantee-compat"
    revision = stored_revision.model_copy(update={"metadata": revision_metadata})
    cur = revision.lifecycle_status
    targets: list[str] = []
    if cur == "proposed":
        targets = ["authorized", "applied"]
    elif cur == "authorized":
        targets = ["applied"]
    elif cur == "applied":
        targets = []
    else:
        raise ValueError(f"cannot apply revision from status {cur!r}")
    for nxt in targets:
        validate_lifecycle_transition("Revision", revision.lifecycle_status, nxt)
        revision.lifecycle_status = nxt  # type: ignore[assignment]
    if store is not None and hasattr(store, "save_record"):
        store.save_record(revision)
    # Preserve the historical in-process helper contract for callers holding
    # the proposal object, while the persisted canonical copy remains the
    # authority used for subsequent operations.
    input_revision.lifecycle_status = revision.lifecycle_status
    input_revision.metadata = dict(revision.metadata)
    return revision


def supersede(
    old_ref: Any,
    new_ref: Any,
    store: Any | None = None,
    *,
    revision: RevisionRecord | str | None = None,
    created_by: str = "system",
) -> RecordRelation:
    """Mark new supersedes old; old object retained."""
    actual_store: Any | None = store
    actual_old = old_ref
    actual_new = new_ref
    actual_revision = revision
    if hasattr(old_ref, "save_record") and hasattr(old_ref, "get_record"):
        actual_store = old_ref
        actual_old = new_ref
        actual_new = store
        if isinstance(actual_new, RevisionRecord) or (isinstance(actual_new, str) and str(actual_new).startswith("revision_")):
            actual_revision = actual_new
            actual_new = None  # type: ignore[assignment]
    old_id = _norm_ref(actual_old) if actual_old is not None else ""
    new_id_val = _norm_ref(actual_new) if actual_new is not None else ""
    rev_id: str | None = None
    if isinstance(actual_revision, RevisionRecord):
        rev_id = actual_revision.id
    elif isinstance(actual_revision, str):
        rev_id = actual_revision
    if not old_id or not new_id_val:
        raise ValueError("supersede requires non-empty old_ref and new_ref")
    if old_id == new_id_val:
        raise ValueError("old_ref and new_ref must differ")
    if actual_store is not None and hasattr(actual_store, "get_record"):
        if actual_revision is None:
            raise ValueError("supersede requires an applied revision authorization")
        revision_record = actual_revision
        revision_ref_id = actual_revision.id if isinstance(actual_revision, RevisionRecord) else actual_revision
        canonical_revision = actual_store.get_record(revision_ref_id) if isinstance(revision_ref_id, str) else None
        if isinstance(canonical_revision, RevisionRecord):
            if isinstance(actual_revision, RevisionRecord) and any(
                getattr(canonical_revision, field, None) != getattr(actual_revision, field, None)
                for field in ("version", "subject_ref", "revises_ref", "produces_ref", "supersedes_ref")
            ):
                raise ValueError("supersede revision endpoints/version do not match canonical state")
            revision_record = canonical_revision
        if not isinstance(revision_record, RevisionRecord):
            raise ValueError("supersede revision proof not found")
        if revision_record.lifecycle_status not in {"applied", "verified", "accepted"}:
            raise ValueError("supersede requires an applied revision")
        auth_ref = revision_record.metadata.get("authorization_ref") if isinstance(revision_record.metadata, dict) else None
        if not isinstance(auth_ref, str) or not auth_ref:
            raise ValueError("supersede revision is missing authorization proof")
        grant = actual_store.get_authorization(auth_ref) if hasattr(actual_store, "get_authorization") else None
        if not isinstance(grant, AuthorizationGrant):
            raise ValueError("supersede authorization proof not found")
        grant_errors = validate_grant(grant)
        expected_versions = [revision_record.id, f"{revision_record.id}:v{revision_record.version}"]
        revision_metadata = revision_record.metadata if isinstance(revision_record.metadata, dict) else {}
        actor_ref = revision_metadata.get("actor_ref")
        if not isinstance(actor_ref, str) or not actor_ref.strip():
            raise ValueError("supersede revision is missing actual actor_ref")
        resource_ref = revision_metadata.get("resource_ref") or revision_record.subject_ref
        effect_class = revision_metadata.get("effect_class") or "write-local"
        request = CanonicalAuthorizationRequest(
            capability="revision.apply",
            actor_ref=actor_ref,
            resource_ref=resource_ref,
            subject_version_refs=expected_versions,
            effect_class=cast(EffectClass, effect_class),
        )
        if grant_errors or not is_authorized_for(request, grant) or not set(expected_versions).intersection(grant.subject_version_refs):
            raise ValueError("supersede authorization proof is invalid")
        old_rec = actual_store.get_record(old_id)
        new_rec = actual_store.get_record(new_id_val)
        if revision_record.revises_ref != old_id or revision_record.produces_ref != new_id_val or revision_record.supersedes_ref != old_id:
            raise ValueError("supersede endpoints do not match the applied revision")
        if old_rec is None or new_rec is None:
            raise ValueError("supersede requires both revision endpoints to exist")
        with actual_store.transaction() if hasattr(actual_store, "transaction") else _nullcontext():
            if old_rec.lifecycle_status == "draft":
                validate_lifecycle_transition(old_rec.record_type, "draft", "current")
                old_rec = old_rec.model_copy(update={"lifecycle_status": "current"})
            validate_lifecycle_transition(old_rec.record_type, old_rec.lifecycle_status, "superseded")
            old_rec = old_rec.model_copy(update={"lifecycle_status": "superseded"})
            if hasattr(actual_store, "save_record"):
                actual_store.save_record(old_rec)
            if new_rec.lifecycle_status == "draft":
                validate_lifecycle_transition(new_rec.record_type, "draft", "current")
                new_rec = new_rec.model_copy(update={"lifecycle_status": "current"})
                actual_store.save_record(new_rec)
            rel = RecordRelation(
                id=new_id("relation"),
                relation_type="supersedes",
                subject_ref=new_id_val,
                object_ref=old_id,
                created_at=datetime.now(UTC),
                created_by=created_by,
                metadata={"revision_ref": rev_id} if rev_id else {},
            )
            if hasattr(actual_store, "save_relation"):
                actual_store.save_relation(rel)
            return rel
    rel = RecordRelation(
        id=new_id("relation"),
        relation_type="supersedes",
        subject_ref=new_id_val,
        object_ref=old_id,
        created_at=datetime.now(UTC),
        created_by=created_by,
        metadata={"revision_ref": rev_id} if rev_id else {},
    )
    return rel


def create_supersedes_relation(
    new_ref: str | Any,
    old_ref: str | Any,
    *,
    created_by: str = "system",
    revision_ref: str | None = None,
) -> RecordRelation:
    return supersede(old_ref, new_ref, store=None, revision=revision_ref, created_by=created_by)
