"""Provenance helpers V1.2."""

from __future__ import annotations

from .models import BaseRecord
from .relations import RecordRelation


def lineage(record_id: str, relations: list[RecordRelation]) -> list[RecordRelation]:
    """Return relations where record_id is subject or object."""
    return [r for r in relations if r.subject_ref == record_id or r.object_ref == record_id]


def provenance_chain(decision_id: str, relations: list[RecordRelation], records: dict[str, BaseRecord]) -> list[str]:
    """Trace Decision -> Authorization -> Action -> Outcome -> Evidence chain."""
    chain = [decision_id]
    # BFS along authorizes/produces/supports edges
    frontier = [decision_id]
    visited = set(frontier)
    while frontier:
        cur = frontier.pop()
        for rel in relations:
            if (
                rel.subject_ref == cur
                and rel.object_ref not in visited
                and rel.relation_type
                in {"authorizes", "produces", "supports", "records", "derived-from"}
            ):
                chain.append(rel.object_ref)
                visited.add(rel.object_ref)
                frontier.append(rel.object_ref)
    return chain


def is_supported(assertion_id: str, relations: list[RecordRelation]) -> bool:
    return any(r.object_ref == assertion_id and r.relation_type == "supports" for r in relations)


def requires_revalidation_refs(change_ref: str, relations: list[RecordRelation]) -> list[str]:
    return [
        r.subject_ref
        for r in relations
        if r.object_ref == change_ref and r.relation_type == "requires-revalidation"
    ]
