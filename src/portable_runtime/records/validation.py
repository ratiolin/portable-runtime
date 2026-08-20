"""Validation V1.2 — semantic invariants."""

from __future__ import annotations

from .models import BaseRecord
from .relations import RecordRelation, validate_relation


def validate_record(record: BaseRecord) -> list[str]:
    errors: list[str] = []
    # 3 orthogonal dimensions must be present
    if not record.record_type:
        errors.append("record_type required")
    if not record.lifecycle_status:
        errors.append("lifecycle_status required")
    # EvidenceArtifact must not have epistemic_status
    if record.record_type == "EvidenceArtifact" and record.epistemic_status is not None:
        errors.append("EvidenceArtifact must not carry epistemic_status")
    # Assertion must have epistemic_status if current
    if record.record_type == "Assertion" and record.lifecycle_status == "current" and record.epistemic_status is None:
        errors.append("Assertion in current must have epistemic_status")
    # Revision must connect versions
    # allow proposed without links, but applied must have revises/produces
    if record.record_type == "Revision":
        pass
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
