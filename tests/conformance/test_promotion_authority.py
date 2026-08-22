"""Promotion authorization must use a typed request, not grant existence."""

from __future__ import annotations

from portable_runtime.protocol.validation import validate_state_graph
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, ChangeObjectRecord, EvidenceArtifact, PolicyRecord


def test_policy_promotion_rejects_grant_for_unrelated_actor() -> None:
    policy = PolicyRecord(
        id="policy_actor_bound",
        lifecycle_status="official",
        metadata={
            "previous_lifecycle_status": "candidate",
            "verification_refs": ["verification_policy_actor"],
            "actor_ref": "agent:actual-promoter",
            "resource_ref": "policy_actor_bound",
            "effect_class": "write-local",
        },
    )
    verification = EvidenceArtifact(
        id="verification_policy_actor",
        kind="closed-verification",
        metadata={"verification_result": {"result": "pass"}},
    )
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:different-promoter",
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
    assert any("structurally bound AuthorizationGrant" in error for error in errors)


def test_knowledge_projection_promotion_requires_canonical_request_binding() -> None:
    assertion = Assertion(id="assertion_projection_auth", statement="claim", lifecycle_status="current")
    judgment = Assertion(id="judgment_projection_auth", statement="judgment", lifecycle_status="current")
    evidence = EvidenceArtifact(id="evidence_projection_auth", kind="check", lifecycle_status="current")
    scope = ChangeObjectRecord(id="scope_projection_auth", lifecycle_status="draft")
    projection_id = "projection_auth_bound"
    projection = KnowledgeProjection(
        id=projection_id,
        lifecycle_status="official",
        current_assertion_refs=[assertion.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[judgment.id],
        scope_version_refs=[scope.id],
        authorization_refs=["grant_projection_auth"],
        validity_scope={"domain": "test"},
        environment_bindings={"runtime": "v1"},
        metadata={
            "actor_ref": "agent:actual-promoter",
            "resource_ref": projection_id,
            "effect_class": "write-local",
        },
    )
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:different-promoter",
        allowed_capabilities=["knowledge.promote"],
        subject_version_refs=[projection_id, f"{projection_id}:v1"],
    )
    grant.id = "grant_projection_auth"
    errors = validate_state_graph(
        {
            "record": [
                assertion.model_dump(mode="json"),
                judgment.model_dump(mode="json"),
                evidence.model_dump(mode="json"),
                scope.model_dump(mode="json"),
            ],
            "knowledge_projection": [projection.model_dump(mode="json")],
            "authorization": [grant.model_dump(mode="json")],
        },
        strict=False,
    )
    assert any("authorization ref" in error and "invalid" in error for error in errors)
