"""EUA-A: freeze the missing experience-use authority boundary.

Audit-only. No production Experience Use API is implied by these tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portable_runtime.core.knowledge import can_promote, promote
from portable_runtime.core.models import KnowledgeItem
from portable_runtime.core.qualification import _KIND_TO_PROOF, _REF_KEYS
from portable_runtime.protocol.validation import validate_state_graph
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, ChangeObjectRecord, Derivation, EvidenceArtifact
from portable_runtime.records.relations import RecordRelation


def test_eua_a_001_knowledge_projection_already_carries_canonical_qualification_graph_refs() -> None:
    fields = set(KnowledgeProjection.model_fields)
    assert {
        "current_assertion_refs",
        "evidence_summary_refs",
        "epistemic_judgment_refs",
        "authorization_refs",
        "scope_version_refs",
        "validity_scope",
        "environment_bindings",
        "counterexample_refs",
        "negative_knowledge_refs",
        "reopen_conditions",
        "lifecycle_status",
    } <= fields


def test_eua_a_002_legacy_knowledge_item_cannot_mint_official_authority() -> None:
    item = KnowledgeItem(
        id="legacy_eua_a",
        kind="doc",
        title="legacy",
        content_ref="external:legacy",
        status="candidate",
    )
    assert can_promote(item) is False
    with pytest.raises(ValueError, match="canonical KnowledgeProjection"):
        promote(item)


def test_eua_a_003_official_projection_truth_is_validated_as_a_typed_bound_graph() -> None:
    claim = Assertion(id="eua_claim", statement="claim", lifecycle_status="current")
    judgment = Assertion(
        id="eua_judgment",
        statement="supported judgment",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={"epistemic_role": "epistemic-judgment", "judgment_for_refs": [claim.id]},
    )
    evidence = EvidenceArtifact(id="eua_evidence", kind="check", lifecycle_status="current")
    scope = ChangeObjectRecord(id="eua_scope", lifecycle_status="draft")
    derivation = Derivation(
        id="eua_derivation",
        premise_refs=[judgment.id],
        evidence_refs=[evidence.id],
        conclusion_ref=claim.id,
        metadata={"scope_version_refs": [scope.id]},
        lifecycle_status="current",
    )
    projection = KnowledgeProjection(
        id="eua_projection",
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[judgment.id],
        authorization_refs=["eua_promotion_grant"],
        scope_version_refs=[scope.id],
        validity_scope={"domain": "eua"},
        environment_bindings={"runtime": "v1"},
        metadata={
            "actor_ref": "agent:eua-promoter",
            "resource_ref": "eua_projection",
            "effect_class": "write-local",
        },
    )
    grant = create_grant_for_approval(
        principal_ref="human:eua-owner",
        grantee_ref="agent:eua-promoter",
        allowed_capabilities=["knowledge.promote"],
        subject_version_refs=[projection.id, f"{projection.id}:v1"],
    )
    grant.id = "eua_promotion_grant"

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
            "authorization": [grant.model_dump(mode="json")],
        },
        strict=False,
    )
    assert not any("knowledge projection" in error.lower() for error in errors), errors


def test_eua_a_004_existing_qualification_vocabulary_does_not_treat_projection_as_use_authority() -> None:
    assert "knowledge_projection_refs" not in _REF_KEYS
    assert "projection_refs" not in _REF_KEYS
    assert "knowledgeprojection" not in _KIND_TO_PROOF


def _source_text() -> str:
    root = Path("src/portable_runtime")
    return "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))


def test_eua_a_005_no_duplicate_experience_qualification_authority_exists() -> None:
    assert "class ExperienceQualification" not in _source_text()


def test_eua_a_006_experience_use_admission_is_not_yet_production() -> None:
    source = _source_text()
    assert "class ExperienceUseAdmission" not in source
    assert "class ExperienceUseRequirement" not in source


def test_eua_a_007_durable_experience_use_snapshot_is_not_yet_production() -> None:
    assert "class ExperienceUseSnapshot" not in _source_text()


def test_eua_a_008_experience_impact_authority_is_not_preopened() -> None:
    source = _source_text()
    assert "ExperienceImpactApplicability" not in source
    assert "ExperienceImpactJudgment" not in source


_EUA_COUNTEREXAMPLES = [
    ("EUA-001", "official projection != usable in this concrete context"),
    ("EUA-002", "retrieval hit != qualified experience use"),
    ("EUA-003", "evidence exists != usable experience"),
    ("EUA-004", "promotion authorization != experience-use or responsibility authorization"),
    ("EUA-005", "experience-use eligibility != permission to execute"),
    ("EUA-006", "scope match != environment/version match"),
    ("EUA-007", "projection identity != immutable currently usable semantic state"),
    ("EUA-008", "caller counterexample absence != canonical counterexample absence"),
    ("EUA-009", "open revalidation/reopen blocker != still usable"),
    ("EUA-010", "deprecated/archived projection != usable experience"),
]


@pytest.mark.parametrize(("case_id", "obligation"), _EUA_COUNTEREXAMPLES, ids=[item[0] for item in _EUA_COUNTEREXAMPLES])
@pytest.mark.xfail(strict=True, reason="EUA-A counterexample freeze; read-only use admission not implemented")
def test_eua_a_counterexamples_require_a_future_real_evaluator(case_id: str, obligation: str) -> None:
    # EUA-A deliberately does not freeze a hypothetical production API. Each
    # obligation must later graduate by being rewritten against the real EUA-B
    # store-owned evaluator rather than by adding audit-only helpers.
    raise AssertionError(f"{case_id}: {obligation}")
