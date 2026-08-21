"""Semantic contract conformance for the canonical record/graph layers."""

from __future__ import annotations

from portable_runtime.records.models import Assertion, PolicyRecord, RevisionRecord
from portable_runtime.records.relations import RecordRelation
from portable_runtime.protocol.validation import validate_state_graph


def test_causes_is_not_a_canonical_relation_type() -> None:
    relation = RecordRelation.model_construct(
        id="relation_causes_contract",
        relation_type="causes",
        subject_ref="action_1",
        object_ref="outcome_1",
    )
    errors = validate_state_graph({"relation": [relation.model_dump(mode="json")]}, strict=False)
    assert any("canonical Runtime relation set" in error for error in errors)


def test_revision_graph_requires_existing_compatible_endpoints() -> None:
    old = Assertion(id="assert_old", statement="old", lifecycle_status="current", epistemic_status="supported")
    revision = RevisionRecord(
        id="revision_missing_new",
        lifecycle_status="applied",
        revises_ref=old.id,
        produces_ref="missing_new",
        supersedes_ref=old.id,
    )
    errors = validate_state_graph(
        {"record": [old.model_dump(mode="json"), revision.model_dump(mode="json")]}, strict=False
    )
    assert any("produces_ref" in error and "missing_new" in error for error in errors)


def test_official_policy_requires_verification_and_authorization_graph_evidence() -> None:
    policy = PolicyRecord(
        id="policy_candidate",
        lifecycle_status="official",
        metadata={"previous_lifecycle_status": "candidate"},
    )
    errors = validate_state_graph({"record": [policy.model_dump(mode="json")]}, strict=False)
    assert any("passing verification" in error for error in errors)
    assert any("effective authorization" in error for error in errors)
