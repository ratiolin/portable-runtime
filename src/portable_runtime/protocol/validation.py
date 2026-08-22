"""Strict state-graph validation for imports and canonical semantic writes.

The runtime stores several record families in one portable state document.  Pydantic
validation proves that each individual object has a valid shape, but it does not
prove that references point at an object that is present, that a revision really
connects two versions, or that two live superseders compete for one predecessor.
This module provides the cross-object validation used by both state and bundle
imports.  It deliberately treats namespaced external references (for example
``evaluator:v9``) as opaque external provenance rather than silently inventing a
local object for them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import cast

from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    EffectClass,
    is_authorized_for,
    validate_grant,
)
from portable_runtime.records.lifecycle import validate_lifecycle_transition
from portable_runtime.records.models import BaseRecord
from portable_runtime.records.relations import RecordRelation, RelationType, validate_relation
from portable_runtime.records.validation import validate_record

_KNOWN_KINDS = {
    "work",
    "run",
    "artifact",
    "evidence",
    "decision",
    "action",
    "outcome",
    "knowledge",
    "knowledge_projection",
    "event",
    "step",
    "attempt",
    "checkpoint",
    "compensation",
    "record",
    "relation",
    "authorization",
}

_EXTERNAL_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*:[^\s]+$")
_EVENT_EXTERNAL_PREFIXES = ("request_", "req_", "invocation_", "capability_")


def _is_external_ref(ref: str, *, event_subject: bool = False) -> bool:
    if _EXTERNAL_REF_RE.match(ref):
        return True
    return event_subject and ref.startswith(_EVENT_EXTERNAL_PREFIXES)


def _kind_for_identifier(identifier: str, state: dict[str, list[dict[str, object]]]) -> str | None:
    """Resolve a state id to its bucket; ``None`` means not local state."""
    for kind, values in state.items():
        for raw in values:
            if isinstance(raw, dict) and raw.get("id") == identifier:
                return kind
    return None


def _record_type_for(identifier: str, state: dict[str, list[dict[str, object]]]) -> str | None:
    for raw in state.get("record", []):
        if isinstance(raw, dict) and raw.get("id") == identifier:
            value = raw.get("record_type")
            return str(value) if value is not None else None
    return None


def _iter_ref_edges(kind: str, raw: dict[str, object]) -> Iterable[tuple[str, str, bool]]:
    """Yield ``(field, ref, event_subject)`` for authoritative local edges.

    Request IDs, provider IDs and free-form user inputs are intentionally not
    treated as state-graph references.  They are execution/provenance values,
    not claims that a local semantic object exists.
    """

    def one(field: str, value: object, *, event_subject: bool = False) -> Iterable[tuple[str, str, bool]]:
        if isinstance(value, str) and value:
            yield field, value, event_subject

    def many(field: str, value: object) -> Iterable[tuple[str, str, bool]]:
        if isinstance(value, list):
            for item in value:
                yield from one(field, item)

    if kind == "work":
        yield from one("parent_work_id", raw.get("parent_work_id"))
        yield from many("artifact_refs", raw.get("artifact_refs"))
    elif kind == "run":
        yield from one("work_id", raw.get("work_id"))
    elif kind == "artifact":
        yield from one("created_by_run_id", raw.get("created_by_run_id"))
    elif kind == "evidence":
        yield from many("subject_refs", raw.get("subject_refs"))
        yield from many("artifact_refs", raw.get("artifact_refs"))
    elif kind == "decision":
        yield from one("work_id", raw.get("work_id"))
        yield from many("rationale_artifact_refs", raw.get("rationale_artifact_refs"))
        yield from many("authorized_by", raw.get("authorized_by"))
    elif kind == "action":
        yield from one("work_id", raw.get("work_id"))
        yield from one("run_id", raw.get("run_id"))
    elif kind == "outcome":
        yield from one("action_id", raw.get("action_id"))
        yield from many("artifact_refs", raw.get("artifact_refs"))
        yield from many("evidence_refs", raw.get("evidence_refs"))
    elif kind == "knowledge":
        yield from one("content_ref", raw.get("content_ref"))
        yield from many("source_work_refs", raw.get("source_work_refs"))
        yield from many("evidence_refs", raw.get("evidence_refs"))
    elif kind == "knowledge_projection":
        for field in (
            "source_work_refs",
            "current_assertion_refs",
            "evidence_summary_refs",
            "counterexample_refs",
            "negative_knowledge_refs",
            "usage_refs",
            "history_refs",
            "epistemic_judgment_refs",
            "authorization_refs",
            "scope_version_refs",
        ):
            yield from many(field, raw.get(field))
    elif kind == "event":
        yield from one("subject_ref", raw.get("subject_ref"), event_subject=True)
    elif kind == "step":
        yield from one("run_id", raw.get("run_id"))
    elif kind == "attempt":
        yield from one("step_id", raw.get("step_id"))
    elif kind == "checkpoint":
        yield from one("run_id", raw.get("run_id"))
        yield from one("step_id", raw.get("step_id"))
        yield from one("payload_ref", raw.get("payload_ref"))
    elif kind == "compensation":
        yield from one("action_ref", raw.get("action_ref"))
        yield from one("result_ref", raw.get("result_ref"))
    elif kind == "record":
        for field in ("source_refs",):
            yield from many(field, raw.get(field))
        record_type = raw.get("record_type")
        if record_type == "Action":
            yield from one("work_id", raw.get("work_id"))
            yield from one("run_id", raw.get("run_id"))
        elif record_type == "Outcome":
            yield from one("action_ref", raw.get("action_ref"))
            yield from many("artifact_refs", raw.get("artifact_refs"))
            yield from many("evidence_refs", raw.get("evidence_refs"))
        elif record_type == "Revision":
            yield from one("subject_ref", raw.get("subject_ref"))
            yield from one("revises_ref", raw.get("revises_ref"))
            yield from one("produces_ref", raw.get("produces_ref"))
            yield from one("supersedes_ref", raw.get("supersedes_ref"))
        elif record_type == "ChangeObject":
            yield from one("current_version_ref", raw.get("current_version_ref"))
        elif record_type == "Decision":
            yield from many("rationale_refs", raw.get("rationale_refs"))
            yield from many("authorized_by", raw.get("authorized_by"))
    elif kind == "relation":
        yield from one("subject_ref", raw.get("subject_ref"))
        yield from one("object_ref", raw.get("object_ref"))
        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            yield from one("revision_ref", metadata.get("revision_ref"))
            yield from one("reopen_assessment_id", metadata.get("reopen_assessment_id"))
    elif kind == "authorization":
        yield from one("source_decision_ref", raw.get("source_decision_ref"))


def _target_shape_ok(
    relation_type: str,
    subject_ref: str,
    object_ref: str,
    subject_kind: str | None,
    object_kind: str | None,
    state: dict[str, list[dict[str, object]]],
) -> bool:
    """Reject only unambiguous relation type mismatches.

    External provenance is intentionally open-ended.  For local objects, the
    stable protocol relations have a small type matrix.  The matrix is kept
    conservative because older bundles legitimately use core records as the
    evidence side of a semantic relation.
    """
    if subject_kind is None or object_kind is None:
        return True
    subject_record = _record_type_for(subject_ref, state) if subject_kind == "record" else None
    object_record = _record_type_for(object_ref, state) if object_kind == "record" else None
    # ``subject_kind``/``object_kind`` are enough for core records.  Semantic
    # record types are resolved by callers below through explicit type lookup.
    if relation_type == "supersedes":
        if subject_kind == object_kind == "record":
            return subject_record == object_record
        return subject_kind == object_kind
    if relation_type == "produces":
        if subject_kind == "record" and subject_record not in {"Action", "Outcome", "ChangeObject", None}:
            return False
        if object_kind == "record" and object_record not in {
            "Outcome",
            "EvidenceArtifact",
            "Observation",
            "ChangeObject",
            None,
        }:
            return False
        return subject_kind in {"action", "work", "run", "record"} and object_kind in {
            "outcome",
            "artifact",
            "evidence",
            "record",
        }
    if relation_type == "authorizes":
        if subject_kind == "record" and subject_record not in {"Decision", "Policy", "Revision", None}:
            return False
        if object_kind == "record" and object_record not in {"Action", "Goal", "ChangeObject", None}:
            return False
        return subject_kind in {"decision", "authorization", "record"} and object_kind in {
            "action",
            "work",
            "run",
            "record",
        }
    if relation_type == "tests":
        if subject_kind == "record" and subject_record not in {"Experiment", "Assertion", None}:
            return False
        return subject_kind == "record" and object_kind in {"record", "evidence", "artifact"}
    return True


def _metadata_refs(raw: dict[str, object], *names: str) -> list[str]:
    metadata = raw.get("metadata")
    values: list[str] = []
    if not isinstance(metadata, dict):
        return values
    for name in names:
        value = metadata.get(name)
        if isinstance(value, str) and value.strip():
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value if isinstance(item, str) and item.strip())
    return values


def _verification_result_is_passing(raw: dict[str, object]) -> bool:
    """Accept only an explicitly typed ClosedVerificationResult proof."""

    metadata = raw.get("metadata")
    nested = raw.get("verification_result")
    kind = raw.get("kind")
    if isinstance(metadata, dict):
        nested = nested or metadata.get("verification_result")
        kind = kind or metadata.get("kind")
    typed_container = kind in {"closed-verification", "verification-result", "ClosedVerificationResult"}
    typed_record = raw.get("record_type") in {"EvidenceArtifact", "VerificationResult"}
    if not (typed_container or typed_record) or not isinstance(nested, dict):
        return False
    result = nested.get("result")
    return isinstance(result, str) and result.lower() == "pass"


def _has_structural_authorization_proof(
    target: dict[str, object],
    state: dict[str, list[dict[str, object]]],
) -> bool:
    target_id = target.get("id")
    if not isinstance(target_id, str):
        return False
    target_version = target.get("version", 1)
    expected_refs = {target_id, f"{target_id}:v{target_version}"}
    for raw in state.get("authorization", []):
        if not isinstance(raw, dict):
            continue
        refs = raw.get("subject_version_refs")
        if not isinstance(refs, list) or not any(str(ref) in expected_refs for ref in refs):
            continue
        # This graph-level check proves shape, binding and non-revocation.  The
        # live boundary remains responsible for current validity windows.
        if raw.get("revoked_at"):
            continue
        try:
            grant = AuthorizationGrant.model_validate(raw)
            if validate_grant(grant):
                continue
            metadata_value = target.get("metadata")
            metadata: dict[str, object] = metadata_value if isinstance(metadata_value, dict) else {}
            record_type = str(target.get("record_type", "")).lower()
            default_capability = {
                "policy": "policy.promote",
                "changeobject": "change.promote",
            }.get(record_type, f"{record_type}.promote")
            capability = str(metadata.get("promotion_capability") or default_capability)
            actor_ref = metadata.get("actor_ref") or grant.grantee_ref
            resource_ref = metadata.get("resource_ref") or target_id
            effect_class = metadata.get("effect_class") or "write-local"
            request = CanonicalAuthorizationRequest(
                capability=capability,
                actor_ref=str(actor_ref),
                resource_ref=str(resource_ref),
                subject_version_refs=sorted(expected_refs),
                effect_class=cast(EffectClass, str(effect_class)),
            )
            if not is_authorized_for(request, grant):
                continue
        except ValueError:
            continue
        return True
    return False


def _has_effective_verification(
    target: dict[str, object],
    state: dict[str, list[dict[str, object]]],
    relations: list[RecordRelation],
) -> bool:
    target_id = target.get("id")
    if not isinstance(target_id, str):
        return False
    metadata_refs = _metadata_refs(target, "verification_refs", "verification_ref", "closed_verification_refs")
    by_id = {
        str(raw.get("id")): raw
        for values in state.values()
        for raw in values
        if isinstance(raw, dict) and isinstance(raw.get("id"), str)
    }
    if metadata_refs and all(ref in by_id and _verification_result_is_passing(by_id[ref]) for ref in metadata_refs):
        return True
    for rel in relations:
        if rel.relation_type not in {"validated-under", "evaluated-by"}:
            continue
        if target_id not in {rel.subject_ref, rel.object_ref}:
            continue
        relation_refs = _metadata_refs(
            {"metadata": rel.metadata},
            "verification_ref",
            "verification_refs",
            "result_ref",
        )
        if relation_refs and all(ref in by_id and _verification_result_is_passing(by_id[ref]) for ref in relation_refs):
            return True
    return False


def validate_state_graph(state: dict[str, list[dict[str, object]]], *, strict: bool = True) -> list[str]:
    """Return all cross-object invariant violations in a state snapshot.

    ``strict=False`` is useful for diagnostics.  Imports and canonical state
    writes use the default strict mode and must reject any returned error.
    """
    errors: list[str] = []
    normalized: dict[str, list[dict[str, object]]] = {kind: list(state.get(kind, [])) for kind in _KNOWN_KINDS}
    ids: dict[str, str] = {}
    duplicate_ids: set[str] = set()
    for kind, values in normalized.items():
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                errors.append(f"{kind}[{index}] must be an object")
                continue
            identifier = raw.get("id")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"{kind}[{index}] missing id")
                continue
            previous = ids.get(identifier)
            if previous is not None:
                duplicate_ids.add(identifier)
                errors.append(f"duplicate id {identifier!r} in {previous} and {kind}")
            else:
                ids[identifier] = kind
    if duplicate_ids:
        # Keep one diagnostic per duplicate id; all references to an ambiguous
        # id are necessarily unsafe and should not be resolved heuristically.
        pass

    # Individual semantic validation and version/revision checks.
    parsed_records: dict[str, BaseRecord] = {}
    for raw in normalized["record"]:
        try:
            record = BaseRecord.model_validate(raw)
            parsed_records[record.id] = record
            errors.extend(f"record {record.id}: {message}" for message in validate_record(record))
            if record.version < 1:
                errors.append(f"record {record.id} has invalid version {record.version}")
            previous_lifecycle = (
                record.metadata.get("previous_lifecycle_status")
                if isinstance(record.metadata, dict)
                else None
            )
            if previous_lifecycle is not None:
                try:
                    validate_lifecycle_transition(record.record_type, str(previous_lifecycle), record.lifecycle_status)
                except ValueError as exc:
                    errors.append(f"record {record.id}: {exc}")
            if record.record_type == "Revision":
                for field in ("revises_ref", "produces_ref", "supersedes_ref"):
                    if (
                        getattr(record, field, None) in (None, "")
                        and record.lifecycle_status not in {"proposed", "rejected"}
                    ):
                        errors.append(f"revision {record.id} missing {field} for lifecycle {record.lifecycle_status}")
                old_ref = getattr(record, "revises_ref", None)
                new_ref = getattr(record, "produces_ref", None)
                if old_ref and new_ref and old_ref == new_ref:
                    errors.append(f"revision {record.id} cannot revise itself")
                md = record.metadata if isinstance(record.metadata, dict) else {}
                if "from_version" in md or "to_version" in md:
                    try:
                        if int(md.get("to_version", 0)) <= int(md.get("from_version", 0)):
                            errors.append(f"revision {record.id} has invalid version lineage")
                    except (TypeError, ValueError):
                        errors.append(f"revision {record.id} has non-numeric version lineage")
        except Exception as exc:
            identifier = raw.get("id", "<unknown>") if isinstance(raw, dict) else "<unknown>"
            errors.append(f"record {identifier}: invalid semantic record: {exc}")

    # Relations must be typed, structurally valid and resolvable.  For unknown
    # external refs we retain provenance without pretending it is local state.
    parsed_relations: list[RecordRelation] = []
    for raw in normalized["relation"]:
        try:
            relation = RecordRelation.model_validate(raw)
            parsed_relations.append(relation)
            if relation.relation_type not in RelationType.__args__:  # type: ignore[attr-defined]
                errors.append(f"relation {relation.id} has invalid relation type {relation.relation_type!r}")
            errors.extend(f"relation {relation.id}: {message}" for message in validate_relation(relation))
            for field, ref, _event_subject in (
                ("subject_ref", relation.subject_ref, False),
                ("object_ref", relation.object_ref, False),
            ):
                if ref in ids or _is_external_ref(ref):
                    continue
                errors.append(f"relation {relation.id} has dangling {field} {ref!r}")
            if relation.relation_type == "supersedes" and relation.subject_ref == relation.object_ref:
                errors.append(f"relation {relation.id} cannot supersede itself")
            subject_kind = ids.get(relation.subject_ref)
            object_kind = ids.get(relation.object_ref)
            if not _target_shape_ok(
                relation.relation_type,
                relation.subject_ref,
                relation.object_ref,
                subject_kind,
                object_kind,
                normalized,
            ):
                errors.append(f"relation {relation.id} target type mismatch for {relation.relation_type}")
        except Exception as exc:
            identifier = raw.get("id", "<unknown>") if isinstance(raw, dict) else "<unknown>"
            if isinstance(raw, dict) and raw.get("relation_type") == "causes":
                errors.append(
                    f"relation {identifier}: relation_type 'causes' is not part of the canonical Runtime relation set"
                )
            errors.append(f"relation {identifier}: invalid relation: {exc}")

    # Strong local references in core records.  Event subjects may be request
    # ids because requests are transient and are represented by Action records.
    for kind, values in normalized.items():
        for raw in values:
            if not isinstance(raw, dict):
                continue
            # ``knowledge`` is the legacy compatibility bucket.  Its
            # ``content_ref`` and evidence refs may intentionally point to
            # external objects that are not part of the portable snapshot;
            # canonical KnowledgeProjection/Record refs are validated through
            # the typed record path above.
            if kind == "knowledge":
                continue
            identifier = raw.get("id", "<unknown>")
            for field, ref, event_subject in _iter_ref_edges(kind, raw):
                if (
                    kind == "record"
                    and raw.get("record_type") == "Revision"
                    and raw.get("lifecycle_status") in {"proposed", "rejected"}
                    and field in {"subject_ref", "revises_ref", "produces_ref", "supersedes_ref"}
                ):
                    # A proposal may name an external version that has not
                    # been imported into this runtime yet.  Once authorized,
                    # endpoint existence/type compatibility is mandatory.
                    continue
                if ref in ids or _is_external_ref(ref, event_subject=event_subject):
                    continue
                # Version labels (v1, commit hashes) are not local object refs;
                # they are checked separately on AuthorizationGrant.
                if kind == "authorization" and field == "source_decision_ref":
                    errors.append(f"authorization {identifier} has dangling source_decision_ref {ref!r}")
                elif kind == "relation" and field in {"revision_ref", "reopen_assessment_id"}:
                    # Assessments are durable only when emitted as a semantic
                    # record; the current reopen implementation carries its
                    # transient ``reopen_*`` id in metadata and journals the
                    # complete assessment separately.
                    if field == "reopen_assessment_id" and ref.startswith("reopen_"):
                        continue
                    if not _is_external_ref(ref):
                        errors.append(f"relation {identifier} has dangling {field} {ref!r}")
                elif kind == "event" and event_subject:
                    continue
                else:
                    errors.append(f"{kind} {identifier} has dangling {field} {ref!r}")

    # Authorization grants are valid only when tied to a concrete subject
    # version.  Empty subject_version_refs would make a grant reusable across
    # revisions and is therefore a fail-closed import error.
    for raw in normalized["authorization"]:
        try:
            grant = AuthorizationGrant.model_validate(raw)
            if not grant.subject_version_refs:
                errors.append(f"authorization {grant.id} missing subject version")
            if any(not isinstance(ref, str) or not ref.strip() for ref in grant.subject_version_refs):
                errors.append(f"authorization {grant.id} has invalid subject version reference")
            source = grant.source_decision_ref
            if source and source not in ids and not _is_external_ref(source):
                errors.append(f"authorization {grant.id} has dangling source_decision_ref {source!r}")
        except Exception as exc:
            identifier = raw.get("id", "<unknown>") if isinstance(raw, dict) else "<unknown>"
            errors.append(f"authorization {identifier}: invalid grant: {exc}")

    # Candidate -> official promotion is a graph-level governance transition:
    # the record itself cannot prove either verification or authorization.
    relation_values = parsed_relations
    for raw in normalized["record"]:
        if not isinstance(raw, dict) or raw.get("lifecycle_status") != "official":
            continue
        if raw.get("record_type") not in {"Policy", "ChangeObject"}:
            continue
        metadata = raw.get("metadata")
        previous = metadata.get("previous_lifecycle_status") if isinstance(metadata, dict) else None
        if previous not in {"candidate", "official"}:
            continue
        identifier = str(raw.get("id", "<unknown>"))
        if isinstance(metadata, dict):
            # Governance refs are authoritative edges.  Do not coerce scalar
            # values or mixed lists into strings during promotion checks.
            for field in (
                "verification_refs",
                "verification_ref",
                "closed_verification_refs",
                "authorization_refs",
                "authorization_ref",
            ):
                if field not in metadata:
                    continue
                value = metadata[field]
                if field.endswith("_ref"):
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"record {identifier} {field} must be a non-empty string")
                elif not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    errors.append(f"record {identifier} {field} must be a list of non-empty strings")
        if not _has_effective_verification(raw, normalized, relation_values):
            errors.append(f"record {identifier} official promotion requires a passing ClosedVerificationResult proof")
        if not _has_structural_authorization_proof(raw, normalized):
            errors.append(f"record {identifier} official promotion requires a structurally bound AuthorizationGrant")

    # KnowledgeProjection promotion is also a governance transition.  Non-
    # empty strings in a projection are not proof; each judgment, evidence,
    # scope-version and authorization ref must resolve to an authoritative
    # local object before an official projection can be committed.
    local_ids = set(ids)
    projection_ref_types: dict[str, set[str]] = {
        "current_assertion_refs": {"Assertion"},
        "evidence_summary_refs": {"EvidenceArtifact", "Observation", "evidence"},
        "epistemic_judgment_refs": {"Assertion"},
        "scope_version_refs": {"Revision", "ChangeObject"},
    }
    for raw in normalized["knowledge_projection"]:
        if not isinstance(raw, dict):
            continue
        identifier = str(raw.get("id", "<unknown>"))
        for field, allowed_types in projection_ref_types.items():
            refs = raw.get(field)
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if not isinstance(ref, str) or ref not in local_ids:
                    continue
                actual_kind = _kind_for_identifier(ref, state)
                actual_type = _record_type_for(ref, state) if actual_kind == "record" else actual_kind
                if actual_type not in allowed_types:
                    errors.append(
                        f"knowledge projection {identifier} {field} ref {ref!r} has type "
                        f"{actual_type!r}, expected one of {sorted(allowed_types)}"
                    )
        auth_refs = raw.get("authorization_refs")
        if isinstance(auth_refs, list):
            for ref in auth_refs:
                if isinstance(ref, str) and ref in local_ids and _kind_for_identifier(ref, state) != "authorization":
                    errors.append(
                        f"knowledge projection {identifier} authorization_refs ref {ref!r} must target authorization"
                    )
        if raw.get("lifecycle_status") != "official":
            continue
        for field in (
            "current_assertion_refs",
            "evidence_summary_refs",
            "epistemic_judgment_refs",
            "scope_version_refs",
        ):
            refs = raw.get(field)
            if not isinstance(refs, list) or not refs:
                errors.append(f"knowledge projection {identifier} official promotion requires {field}")
                continue
            for ref in refs:
                if not isinstance(ref, str) or ref not in local_ids:
                    errors.append(f"knowledge projection {identifier} has unresolved {field} ref {ref!r}")
        auth_refs = raw.get("authorization_refs")
        if not isinstance(auth_refs, list) or not auth_refs:
            errors.append(f"knowledge projection {identifier} official promotion requires authorization_refs")
        else:
            for ref in auth_refs:
                grant_raw = next(
                    (item for item in normalized["authorization"] if isinstance(item, dict) and item.get("id") == ref),
                    None,
                )
                if grant_raw is None:
                    errors.append(f"knowledge projection {identifier} has unresolved authorization ref {ref!r}")
                else:
                    try:
                        grant = AuthorizationGrant.model_validate(grant_raw)
                        grant_errors = validate_grant(grant)
                        projection_metadata_value = raw.get("metadata")
                        projection_metadata: dict[str, object] = (
                            projection_metadata_value if isinstance(projection_metadata_value, dict) else {}
                        )
                        actor_ref = projection_metadata.get("actor_ref") or grant.grantee_ref
                        resource_ref = projection_metadata.get("resource_ref") or identifier
                        effect_class = projection_metadata.get("effect_class") or "write-local"
                        capability = projection_metadata.get("promotion_capability") or "knowledge.promote"
                        request = CanonicalAuthorizationRequest(
                            capability=str(capability),
                            actor_ref=str(actor_ref),
                            resource_ref=str(resource_ref),
                            subject_version_refs=[identifier, f"{identifier}:v1"],
                            effect_class=cast(EffectClass, str(effect_class)),
                        )
                        if grant_errors or not is_authorized_for(request, grant):
                            errors.append(f"knowledge projection {identifier} authorization ref {ref!r} is invalid")
                    except Exception:
                        errors.append(f"knowledge projection {identifier} authorization ref {ref!r} is invalid")

    # Revision endpoints must exist locally and remain type-compatible.  The
    # single-object validator cannot prove this because it has no graph.
    for record in parsed_records.values():
        if record.record_type != "Revision":
            continue
        if record.lifecycle_status in {"authorized", "applied", "verified", "accepted"}:
            metadata = record.metadata if isinstance(record.metadata, dict) else {}
            raw_refs = (
                metadata.get("authorization_ref")
                or metadata.get("authorization_refs")
                or metadata.get("authorization_grant_id")
            )
            auth_refs = (
                [raw_refs]
                if isinstance(raw_refs, str)
                else list(raw_refs or [])
                if isinstance(raw_refs, list)
                else []
            )
            grants_by_id = {
                str(raw.get("id")): raw
                for raw in normalized["authorization"]
                if isinstance(raw, dict) and isinstance(raw.get("id"), str)
            }
            if len(auth_refs) != 1 or auth_refs[0] not in grants_by_id:
                errors.append(f"revision {record.id} {record.lifecycle_status} requires a valid authorization_ref")
            else:
                try:
                    grant = AuthorizationGrant.model_validate(grants_by_id[auth_refs[0]])
                    grant_errors = validate_grant(grant)
                    if grant_errors:
                        errors.extend(f"revision {record.id}: {error}" for error in grant_errors)
                    expected_versions = {record.id, f"{record.id}:v{record.version}"}
                    if not expected_versions.intersection(grant.subject_version_refs):
                        errors.append(f"revision {record.id} authorization does not bind this revision version")
                    revision_metadata = record.metadata if isinstance(record.metadata, dict) else {}
                    actor_ref = revision_metadata.get("actor_ref")
                    resource_ref = revision_metadata.get("resource_ref") or getattr(record, "subject_ref", "")
                    effect_class = revision_metadata.get("effect_class")
                    if not isinstance(actor_ref, str) or not actor_ref.strip():
                        errors.append(f"revision {record.id} authorization missing actual actor_ref")
                    if not isinstance(resource_ref, str) or not resource_ref.strip():
                        errors.append(f"revision {record.id} authorization missing resource_ref")
                    if not isinstance(effect_class, str) or not effect_class.strip():
                        errors.append(f"revision {record.id} authorization missing effect_class")
                    if (
                        isinstance(actor_ref, str)
                        and isinstance(resource_ref, str)
                        and isinstance(effect_class, str)
                    ):
                        request = CanonicalAuthorizationRequest(
                            capability="revision.apply",
                            actor_ref=actor_ref,
                            resource_ref=resource_ref,
                            subject_version_refs=sorted(expected_versions),
                            effect_class=cast(EffectClass, effect_class),
                        )
                        if not is_authorized_for(request, grant):
                            errors.append(
                                f"revision {record.id} authorization does not authorize actor/resource/effect"
                            )
                except Exception as exc:
                    errors.append(f"revision {record.id} authorization is invalid: {exc}")
        old_ref = getattr(record, "revises_ref", None)
        new_ref = getattr(record, "produces_ref", None)
        if not old_ref or not new_ref or record.lifecycle_status in {"proposed", "rejected"}:
            continue
        old_record = parsed_records.get(old_ref)
        new_record = parsed_records.get(new_ref)
        if old_record is None:
            errors.append(f"revision {record.id} revises_ref {old_ref!r} is not a local record")
        if new_record is None:
            errors.append(f"revision {record.id} produces_ref {new_ref!r} is not a local record")
        if old_record is not None and new_record is not None and old_record.record_type != new_record.record_type:
            errors.append(f"revision {record.id} old/new record types are incompatible")

    # A supersedes edge is an effect of an applied, authorized Revision.  A
    # bare relation is not sufficient provenance: without the typed revision
    # proof, the graph cannot establish who authorized the replacement or
    # which endpoints were actually changed.
    for relation in parsed_relations:
        if relation.relation_type != "supersedes":
            continue
        metadata = relation.metadata if isinstance(relation.metadata, dict) else {}
        revision_ref = metadata.get("revision_ref")
        if not isinstance(revision_ref, str) or not revision_ref.strip():
            errors.append(f"supersedes relation {relation.id} requires revision_ref")
            continue
        revision = parsed_records.get(revision_ref)
        if not isinstance(revision, BaseRecord) or revision.record_type != "Revision":
            errors.append(f"supersedes relation {relation.id} revision_ref {revision_ref!r} must target Revision")
            continue
        if revision.lifecycle_status not in {"applied", "verified", "accepted"}:
            errors.append(f"supersedes relation {relation.id} requires an applied authorized Revision")
        if (
            getattr(revision, "produces_ref", None) != relation.subject_ref
            or getattr(revision, "revises_ref", None) != relation.object_ref
        ):
            errors.append(f"supersedes relation {relation.id} endpoints do not match revision {revision.id}")
        revision_metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
        auth_ref = revision_metadata.get("authorization_ref")
        actor_ref = revision_metadata.get("actor_ref")
        resource_ref = revision_metadata.get("resource_ref") or getattr(revision, "subject_ref", "")
        effect_class = revision_metadata.get("effect_class")
        grant_raw = next(
            (item for item in normalized["authorization"] if isinstance(item, dict) and item.get("id") == auth_ref),
            None,
        )
        if not isinstance(grant_raw, dict):
            errors.append(f"supersedes relation {relation.id} revision authorization proof not found")
            continue
        try:
            grant = AuthorizationGrant.model_validate(grant_raw)
            request = CanonicalAuthorizationRequest(
                capability="revision.apply",
                actor_ref=actor_ref if isinstance(actor_ref, str) else "",
                resource_ref=resource_ref if isinstance(resource_ref, str) else "",
                subject_version_refs=[revision.id, f"{revision.id}:v{revision.version}"],
                effect_class=cast(EffectClass, effect_class if isinstance(effect_class, str) else ""),
            )
            if validate_grant(grant) or not is_authorized_for(request, grant):
                errors.append(f"supersedes relation {relation.id} revision authorization proof is invalid")
        except Exception as exc:
            errors.append(f"supersedes relation {relation.id} revision authorization proof is invalid: {exc}")

    # More than one active superseder for a predecessor is ambiguous lineage.
    superseders: dict[str, list[str]] = defaultdict(list)
    lifecycle_by_id = {identifier: rec.lifecycle_status for identifier, rec in parsed_records.items()}
    for relation in parsed_relations:
        if relation.relation_type != "supersedes":
            continue
        subject_status = lifecycle_by_id.get(relation.subject_ref)
        if subject_status in {"superseded", "archived", "deprecated", "rejected", "rolled-back"}:
            continue
        superseders[relation.object_ref].append(relation.subject_ref)
    for predecessor, subjects in superseders.items():
        unique_subjects = sorted(set(subjects))
        if len(unique_subjects) > 1:
            errors.append(f"duplicate active superseder for {predecessor!r}: {', '.join(unique_subjects)}")

    # Supersedes edges form a lineage, not a cycle.  A cycle would make the
    # current version non-deterministic even when each edge is individually
    # well-shaped.
    supersedes_graph: dict[str, list[str]] = defaultdict(list)
    for relation in parsed_relations:
        if relation.relation_type == "supersedes" and relation.subject_ref in ids and relation.object_ref in ids:
            supersedes_graph[relation.subject_ref].append(relation.object_ref)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"supersedes lineage contains a cycle at {node!r}")
            return
        if node in visited:
            return
        visiting.add(node)
        for predecessor in supersedes_graph.get(node, []):
            visit(predecessor)
        visiting.remove(node)
        visited.add(node)

    for node in supersedes_graph:
        visit(node)

    return errors


def assert_valid_state_graph(state: dict[str, list[dict[str, object]]]) -> None:
    errors = validate_state_graph(state)
    if errors:
        raise ValueError("state graph validation failed: " + "; ".join(errors))


def assert_valid_candidate_write(
    state: dict[str, list[dict[str, object]]],
    kind: str,
    value: object,
) -> None:
    """Validate one normal write against the complete candidate graph.

    Import-time validation alone permits a running store to temporarily hold a
    graph that cannot be exported and re-imported.  Every canonical semantic
    mutation uses this merge-and-validate operation before committing.
    """

    if kind not in _KNOWN_KINDS:
        raise ValueError(f"unknown state graph bucket {kind!r}")
    if not hasattr(value, "model_dump") or not isinstance(getattr(value, "id", None), str):
        raise ValueError(f"{kind} writes require a model with a string id")
    candidate = {bucket: list(values) for bucket, values in state.items()}
    candidate.setdefault(kind, [])
    value_id = str(value.id)  # type: ignore[attr-defined]
    candidate[kind] = [
        raw for raw in candidate[kind]
        if not isinstance(raw, dict) or raw.get("id") != value_id
    ]
    candidate[kind].append(value.model_dump(mode="json"))  # type: ignore[attr-defined]
    assert_valid_state_graph(candidate)


def validate_record_write(record: BaseRecord, existing: BaseRecord | None = None) -> list[str]:
    """Validate lifecycle/version invariants available on one canonical write."""
    errors = list(validate_record(record))
    if record.version < 1:
        errors.append(f"record {record.id} has invalid version {record.version}")
    metadata = record.metadata if isinstance(record.metadata, dict) else {}
    previous = metadata.get("previous_lifecycle_status")
    if previous is not None:
        try:
            validate_lifecycle_transition(record.record_type, str(previous), record.lifecycle_status)
        except ValueError as exc:
            errors.append(str(exc))
    if existing is not None and existing.id == record.id:
        # Equal version is allowed only for an idempotent replay.  A changed
        # payload must advance the lineage version instead of silently
        # overwriting an authoritative semantic fact.
        old_dump = existing.model_dump(mode="json")
        new_dump = record.model_dump(mode="json")
        old_dump.pop("created_at", None)
        new_dump.pop("created_at", None)
        if old_dump != new_dump and record.version <= existing.version:
            errors.append(
                f"record {record.id} version must advance beyond {existing.version} for a changed semantic write"
            )
    return errors
