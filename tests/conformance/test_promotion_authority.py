"""Promotion authorization must use a typed request, not grant existence."""

from __future__ import annotations

from portable_runtime.protocol.validation import validate_state_graph
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, ChangeObjectRecord, EvidenceArtifact, PolicyRecord
from portable_runtime.records.models import Derivation
from portable_runtime.records.relations import RecordRelation


def test_policy_promotion_capability_cannot_be_selected_by_metadata() -> None:
    policy = PolicyRecord(
        id="policy_capability_fixed",
        lifecycle_status="official",
        metadata={
            "previous_lifecycle_status": "candidate",
            "verification_refs": ["verification_policy_capability_fixed"],
            "actor_ref": "agent:promoter",
            "resource_ref": "policy_capability_fixed",
            "effect_class": "write-local",
            "promotion_capability": "change.promote",
        },
    )
    verification = EvidenceArtifact(
        id="verification_policy_capability_fixed",
        kind="closed-verification",
        metadata={"verification_result": {"result": "pass"}},
    )
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:promoter",
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
    assert not any("structurally bound AuthorizationGrant" in error for error in errors)


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


def test_policy_promotion_rejects_missing_actual_action_facts() -> None:
    policy = PolicyRecord(
        id="policy_missing_action_facts",
        lifecycle_status="official",
        metadata={
            "previous_lifecycle_status": "candidate",
            "verification_refs": ["verification_missing_action_facts"],
        },
    )
    verification = EvidenceArtifact(
        id="verification_missing_action_facts",
        kind="closed-verification",
        metadata={"verification_result": {"result": "pass"}},
    )
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:promoter",
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


def test_knowledge_projection_rejects_approval_assertion_as_epistemic_judgment() -> None:
    claim = Assertion(id="projection_claim_binding", statement="claim", lifecycle_status="current")
    approval = Assertion(
        id="projection_approval_binding",
        statement="approved",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={"role": "approval", "judgment_for_refs": [claim.id]},
    )
    evidence = EvidenceArtifact(id="projection_evidence_binding", kind="check", lifecycle_status="current")
    scope = ChangeObjectRecord(id="projection_scope_binding", lifecycle_status="draft")
    derivation = Derivation(
        id="projection_derivation_binding",
        premise_refs=[approval.id],
        evidence_refs=[evidence.id],
        conclusion_ref=claim.id,
        metadata={"scope_version_refs": [scope.id]},
        lifecycle_status="current",
    )
    projection = KnowledgeProjection(
        id="projection_epistemic_binding",
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[approval.id],
        authorization_refs=[],
        scope_version_refs=[scope.id],
        validity_scope={"domain": "test"},
        environment_bindings={"runtime": "v1"},
    )
    errors = validate_state_graph(
        {
            "record": [
                claim.model_dump(mode="json"),
                approval.model_dump(mode="json"),
                evidence.model_dump(mode="json"),
                scope.model_dump(mode="json"),
                derivation.model_dump(mode="json"),
            ],
            "relation": [
                RecordRelation(
                    relation_type="derived-from",
                    subject_ref=claim.id,
                    object_ref=approval.id,
                ).model_dump(mode="json"),
                RecordRelation(
                    relation_type="scoped-to",
                    subject_ref=derivation.id,
                    object_ref=scope.id,
                ).model_dump(mode="json"),
            ],
            "knowledge_projection": [projection.model_dump(mode="json")],
        },
        strict=False,
    )
    assert any("approval assertion" in error for error in errors)


def test_knowledge_projection_epistemic_binding_accepts_complete_derivation() -> None:
    claim = Assertion(id="projection_claim_complete", statement="claim", lifecycle_status="current")
    judgment = Assertion(
        id="projection_judgment_complete",
        statement="judgment",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={"epistemic_role": "epistemic-judgment", "judgment_for_refs": [claim.id]},
    )
    evidence = EvidenceArtifact(id="projection_evidence_complete", kind="check", lifecycle_status="current")
    scope = ChangeObjectRecord(id="projection_scope_complete", lifecycle_status="draft")
    derivation = Derivation(
        id="projection_derivation_complete",
        premise_refs=[judgment.id],
        evidence_refs=[evidence.id],
        conclusion_ref=claim.id,
        metadata={"scope_version_refs": [scope.id]},
        lifecycle_status="current",
    )
    projection = KnowledgeProjection(
        id="projection_complete_binding",
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[judgment.id],
        authorization_refs=[],
        scope_version_refs=[scope.id],
        validity_scope={"domain": "test"},
        environment_bindings={"runtime": "v1"},
    )
    errors = validate_state_graph(
        {
            "record": [
                claim.model_dump(mode="json"),
                judgment.model_dump(mode="json"),
                evidence.model_dump(mode="json"),
                scope.model_dump(mode="json"),
                derivation.model_dump(mode="json"),
            ],
            "relation": [
                RecordRelation(
                    relation_type="derived-from",
                    subject_ref=claim.id,
                    object_ref=judgment.id,
                ).model_dump(mode="json"),
                RecordRelation(
                    relation_type="scoped-to",
                    subject_ref=derivation.id,
                    object_ref=scope.id,
                ).model_dump(mode="json"),
            ],
            "knowledge_projection": [projection.model_dump(mode="json")],
        },
        strict=False,
    )
    assert not any("lacks judgment/derivation/evidence/scope binding" in error for error in errors)


def test_knowledge_projection_epistemic_binding_rejects_unproven_judgment_shapes() -> None:
    claim = Assertion(id="projection_claim_invalid", statement="claim", lifecycle_status="current")
    wrong_type = ChangeObjectRecord(id="projection_judgment_wrong_type", lifecycle_status="draft")
    unsupported = Assertion(
        id="projection_judgment_unsupported",
        statement="not supported",
        lifecycle_status="current",
        epistemic_status="unverified",
        metadata={"epistemic_role": "epistemic-judgment", "judgment_for_refs": [claim.id]},
    )
    projection = KnowledgeProjection(
        id="projection_invalid_binding",
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[],
        epistemic_judgment_refs=[wrong_type.id, unsupported.id],
        authorization_refs=[],
        scope_version_refs=[],
        validity_scope={"domain": "test"},
        environment_bindings={"runtime": "v1"},
    )
    errors = validate_state_graph(
        {
            "record": [claim.model_dump(mode="json"), wrong_type.model_dump(mode="json"), unsupported.model_dump(mode="json")],
            "knowledge_projection": [projection.model_dump(mode="json")],
        },
        strict=False,
    )
    assert any("must target Assertion" in error for error in errors)
    assert any("must carry supported epistemic_status" in error for error in errors)
    assert any("lacks judgment/derivation/evidence/scope binding" in error for error in errors)
