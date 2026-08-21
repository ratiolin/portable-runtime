"""Revision / Version Lineage — R1.3 implementation milestone.

Preserves old objects and never silently overwrites an authoritative version.

Implements:
  Revision(revises -> old, produces -> new)
  new supersedes -> old

Old objects are retained; supersede mutates lifecycle_status to superseded.
Provides create_revision, apply_revision, supersede.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from portable_runtime.core.models import new_id
from portable_runtime.records.authorization import AuthorizationGrant, validate_grant
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
) -> RevisionRecord:
    """Advance a revision toward ``applied`` with an explicit grant proof.

    Revision lifecycle helpers do not manufacture authorization.  A durable
    grant must already exist in ``store`` and bind this revision id/version.
    """
    if store is None or not hasattr(store, "get_authorization"):
        raise ValueError("apply_revision requires a state store and authorization_ref")
    grant_ref = authorization_ref
    if isinstance(grant_ref, AuthorizationGrant):
        grant = grant_ref
        grant_id = grant.id
    elif isinstance(grant_ref, str) and grant_ref:
        grant_id = grant_ref
        grant = store.get_authorization(grant_ref)
    else:
        grant_id = None
        grant = None
    if not isinstance(grant, AuthorizationGrant):
        raise ValueError("apply_revision requires an existing AuthorizationGrant")
    grant_errors = validate_grant(grant)
    expected_versions = {revision.id, f"{revision.id}:v{revision.version}"}
    if grant_errors or not expected_versions.intersection(grant.subject_version_refs):
        detail = "; ".join(grant_errors) if grant_errors else "grant does not bind this revision version"
        raise ValueError(f"revision authorization rejected: {detail}")
    revision.metadata = {**revision.metadata, "authorization_ref": grant_id}
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
        if isinstance(actual_revision, str):
            revision_record = actual_store.get_record(actual_revision)
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
        expected_versions = {revision_record.id, f"{revision_record.id}:v{revision_record.version}"}
        if grant_errors or not expected_versions.intersection(grant.subject_version_refs):
            raise ValueError("supersede authorization proof is invalid")
        old_rec = actual_store.get_record(old_id)
        new_rec = actual_store.get_record(new_id_val)
        if old_rec is not None:
            if old_rec.lifecycle_status == "draft":
                validate_lifecycle_transition(old_rec.record_type, "draft", "current")
                old_rec = old_rec.model_copy(update={"lifecycle_status": "current"})
            validate_lifecycle_transition(old_rec.record_type, old_rec.lifecycle_status, "superseded")
            old_rec = old_rec.model_copy(update={"lifecycle_status": "superseded"})
            if hasattr(actual_store, "save_record"):
                actual_store.save_record(old_rec)
        if new_rec is not None and new_rec.lifecycle_status == "draft":
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
    if actual_store is not None and hasattr(actual_store, "save_relation"):
        actual_store.save_relation(rel)
    return rel


def create_supersedes_relation(
    new_ref: str | Any,
    old_ref: str | Any,
    *,
    created_by: str = "system",
    revision_ref: str | None = None,
) -> RecordRelation:
    return supersede(old_ref, new_ref, store=None, revision=revision_ref, created_by=created_by)
