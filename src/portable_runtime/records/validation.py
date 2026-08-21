"""Validation V1.2 — semantic invariants."""

from __future__ import annotations

from .models import BaseRecord
from .relations import RecordRelation, validate_relation


def _has_observation_provenance(record: BaseRecord) -> bool:
    """Return whether an Observation carries explicit acquisition provenance."""

    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    for key in ("acquisition_provenance", "acquisition_ref", "collector_ref", "instrument_ref"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, tuple, dict)) and bool(value):
            return True
    return False


def validate_canonical_write(record: BaseRecord) -> list[str]:
    """Reject undeclared top-level fields on normal canonical writes.

    ``BaseRecord`` stays permissive so legacy/import adapters can preserve
    forward fields.  Store ``save_record`` paths call this stricter contract;
    state/bundle imports validate and retain unknown fields explicitly at the
    compatibility boundary instead of silently promoting them into the write
    protocol.
    """

    extra = getattr(record, "model_extra", None) or {}
    if extra:
        return [
            "canonical record writes forbid undeclared fields: "
            + ", ".join(sorted(str(key) for key in extra))
        ]
    return []


def validate_record(record: BaseRecord) -> list[str]:
    errors: list[str] = []
    # 3 orthogonal dimensions must be present
    if not record.record_type:
        errors.append("record_type required")
    if not record.lifecycle_status:
        errors.append("lifecycle_status required")
    # EvidenceArtifact must not have epistemic_status.  The model validator
    # catches ordinary construction; this duplicate check keeps import and
    # model_construct paths fail-closed at the semantic layer too.
    if record.record_type == "EvidenceArtifact" and record.epistemic_status is not None:
        errors.append("EvidenceArtifact must not carry epistemic_status")
    if record.record_type == "Observation" and not record.source_refs and not _has_observation_provenance(record):
        errors.append("Observation requires source_refs or explicit acquisition provenance")
    # Assertion must have epistemic_status if current
    if record.record_type == "Assertion" and record.lifecycle_status == "current" and record.epistemic_status is None:
        errors.append("Assertion in current must have epistemic_status")
    # Revision links may be incomplete while proposed/rejected, but every
    # effective revision must identify the old, new and superseded versions.
    if record.record_type == "Revision":
        if record.lifecycle_status not in {"proposed", "rejected"}:
            for field in ("revises_ref", "produces_ref", "supersedes_ref"):
                if not getattr(record, field, None):
                    errors.append(f"Revision {record.id} requires {field} outside proposed/rejected")
            revises_ref = getattr(record, "revises_ref", None)
            produces_ref = getattr(record, "produces_ref", None)
            if revises_ref and produces_ref and revises_ref == produces_ref:
                errors.append("Revision revises_ref and produces_ref must differ")
    # lifecycle transition check if version >1
    # (actual transition validated externally via lifecycle module)
    return errors


def validate_record_graph(records: list[BaseRecord], relations: list[RecordRelation]) -> list[str]:
    errors: list[str] = []
    ids = {r.id for r in records}
    for rel in relations:
        errors.extend(validate_relation(rel))
        # produces != causes already checked
        if rel.subject_ref not in ids and not rel.subject_ref.startswith(("work_", "run_", "step_")):
            # allow refs to external Work/Run but flag missing record for strict graph
            pass
        if rel.object_ref not in ids and not rel.object_ref.startswith(("work_", "run_", "step_")):
            pass
    # Check for lifecycle ep incorrectly carrying
    for r in records:
        errors.extend(validate_record(r))
    return errors
