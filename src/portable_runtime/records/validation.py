"""Runtime semantic-record validation for Framework V1 / schema official-1.0.0.

Single-record and canonical-write invariants live here.  Graph-level
invariants are owned by :mod:`portable_runtime.protocol.validation`.
"""

from __future__ import annotations

from .models import BaseRecord
from .relations import RecordRelation


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

    errors: list[str] = []
    extra = getattr(record, "model_extra", None) or {}
    if extra:
        errors.append(
            "canonical record writes forbid undeclared fields: "
            + ", ".join(sorted(str(key) for key in extra))
        )
    if record.record_type == "Outcome" and record.lifecycle_status == "confirmed":
        errors.append(
            "confirmed Outcome requires verified-outcome authority commit"
        )
    return errors


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
    """Deprecated compatibility wrapper for the authoritative graph validator.

    New callers must use ``protocol.validation.validate_state_graph`` directly.
    Keeping this adapter prevents legacy imports from silently falling back to
    the former weak graph checks while preserving the old return shape.
    """

    from portable_runtime.protocol.validation import validate_state_graph

    return validate_state_graph(
        {
            "record": [record.model_dump(mode="json") for record in records],
            "relation": [relation.model_dump(mode="json") for relation in relations],
        },
        strict=False,
    )
