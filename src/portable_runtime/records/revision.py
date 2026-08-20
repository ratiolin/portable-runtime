"""Revision / Version Lineage V1.3 — preserves old object, no silent overwrite.

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
) -> RevisionRecord:
    """Advance revision lifecycle toward applied."""
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
        old_rec = actual_store.get_record(old_id)
        new_rec = actual_store.get_record(new_id_val)
        if old_rec is not None:
            try:
                validate_lifecycle_transition(old_rec.record_type, old_rec.lifecycle_status, "superseded")
                old_rec.lifecycle_status = "superseded"  # type: ignore[assignment]
                if hasattr(actual_store, "save_record"):
                    actual_store.save_record(old_rec)
            except ValueError:
                if old_rec.lifecycle_status == "draft":
                    try:
                        validate_lifecycle_transition(old_rec.record_type, "draft", "current")
                        old_rec.lifecycle_status = "current"  # type: ignore[assignment]
                        validate_lifecycle_transition(old_rec.record_type, "current", "superseded")
                        old_rec.lifecycle_status = "superseded"  # type: ignore[assignment]
                        actual_store.save_record(old_rec)
                    except ValueError:
                        old_rec.lifecycle_status = "superseded"  # type: ignore[assignment]
                        actual_store.save_record(old_rec)
                else:
                    old_rec.lifecycle_status = "superseded"  # type: ignore[assignment]
                    actual_store.save_record(old_rec)
        if new_rec is not None and new_rec.lifecycle_status == "draft":
            try:
                validate_lifecycle_transition(new_rec.record_type, "draft", "current")
                new_rec.lifecycle_status = "current"  # type: ignore[assignment]
                actual_store.save_record(new_rec)
            except ValueError:
                pass
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
