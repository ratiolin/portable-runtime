"""Semantic contract conformance for the canonical record/graph layers."""

from __future__ import annotations

from portable_runtime.records.authorization import AuthorizationGrant
from portable_runtime.records.models import Assertion, EvidenceArtifact, PolicyRecord, RevisionRecord
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.validation import validate_record_graph
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
    assert any("ClosedVerificationResult" in error for error in errors)
    assert any("AuthorizationGrant" in error for error in errors)


def test_official_policy_rejects_open_support_and_bare_authorizes_edges() -> None:
    policy = PolicyRecord(
        id="policy_shortcut",
        lifecycle_status="official",
        version=1,
        metadata={"previous_lifecycle_status": "candidate", "result": "pass"},
    )
    open_support = RecordRelation(
        id="support_shortcut",
        relation_type="supports",
        subject_ref="assertion_support",
        object_ref=policy.id,
        metadata={"result": "pass"},
    )
    bare_authorizes = RecordRelation(
        id="authorizes_shortcut",
        relation_type="authorizes",
        subject_ref="decision_shortcut",
        object_ref=policy.id,
    )
    errors = validate_state_graph(
        {"record": [policy.model_dump(mode="json")], "relation": [open_support.model_dump(mode="json"), bare_authorizes.model_dump(mode="json")]},
        strict=False,
    )
    assert any("ClosedVerificationResult" in error for error in errors)
    assert any("AuthorizationGrant" in error for error in errors)


def test_official_policy_accepts_typed_closed_verification_and_version_bound_grant() -> None:
    policy = PolicyRecord(
        id="policy_verified",
        lifecycle_status="official",
        version=1,
        metadata={"previous_lifecycle_status": "candidate", "verification_refs": ["verification_closed"]},
    )
    verification = EvidenceArtifact(
        id="verification_closed",
        kind="closed-verification",
        metadata={"verification_result": {"result": "pass"}},
    )
    grant = AuthorizationGrant(
        id="grant_policy_verified",
        principal_ref="owner",
        grantee_ref="runtime",
        allowed_capabilities=["policy.promote"],
        subject_version_refs=[f"{policy.id}:v{policy.version}"],
    )
    errors = validate_state_graph(
        {
            "record": [policy.model_dump(mode="json"), verification.model_dump(mode="json")],
            "authorization": [grant.model_dump(mode="json")],
        },
        strict=False,
    )
    assert not any("ClosedVerificationResult" in error for error in errors)
    assert not any("AuthorizationGrant" in error for error in errors)


def test_legacy_record_graph_entrypoint_delegates_to_strict_protocol_owner() -> None:
    record = Assertion(id="assert_graph", statement="graph", lifecycle_status="draft")
    relation = RecordRelation(
        id="dangling_graph_relation",
        relation_type="supports",
        subject_ref=record.id,
        object_ref="missing_graph_target",
    )
    errors = validate_record_graph([record], [relation])
    assert any("missing_graph_target" in error for error in errors)
