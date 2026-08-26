from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from portable_runtime.experience.use_admission import (
    ExperienceUseAdmission,
    ExperienceUseAdmissionEvaluator,
    ExperienceUseRequirement,
)
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, ChangeObjectRecord, Derivation, EvidenceArtifact
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore


def _seed_official(
    store: InMemoryStateStore,
    *,
    projection_id: str = "eua_projection",
    counterexample: bool = False,
) -> dict[str, object]:
    claim = Assertion(
        id=f"{projection_id}_claim",
        statement="settled claim",
        lifecycle_status="current",
        epistemic_status="supported",
    )
    judgment = Assertion(
        id=f"{projection_id}_judgment",
        statement="experience supports claim",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={
            "epistemic_role": "epistemic-judgment",
            "judgment_for_refs": [claim.id],
        },
    )
    evidence = EvidenceArtifact(
        id=f"{projection_id}_evidence",
        kind="check",
        lifecycle_status="current",
    )
    scope = ChangeObjectRecord(
        id=f"{projection_id}_scope_v1",
        lifecycle_status="draft",
    )
    derivation = Derivation(
        id=f"{projection_id}_derivation",
        premise_refs=[judgment.id],
        evidence_refs=[evidence.id],
        conclusion_ref=claim.id,
        metadata={"scope_version_refs": [scope.id]},
        lifecycle_status="current",
    )
    for record in (claim, judgment, evidence, scope, derivation):
        store.save_record(record)
    store.save_relation(
        RecordRelation(
            id=f"{projection_id}_derived",
            relation_type="derived-from",
            subject_ref=claim.id,
            object_ref=judgment.id,
        )
    )
    store.save_relation(
        RecordRelation(
            id=f"{projection_id}_scoped",
            relation_type="scoped-to",
            subject_ref=derivation.id,
            object_ref=scope.id,
        )
    )

    challenge: Assertion | None = None
    counterexample_refs: list[str] = []
    if counterexample:
        challenge = Assertion(
            id=f"{projection_id}_counterexample",
            kind="challenge",
            statement="known counterexample",
            lifecycle_status="current",
            epistemic_status="supported",
        )
        store.save_record(challenge)
        counterexample_refs.append(challenge.id)

    grant = create_grant_for_approval(
        principal_ref="human:eua-owner",
        grantee_ref="agent:eua-promoter",
        allowed_capabilities=["knowledge.promote"],
        subject_version_refs=[projection_id, f"{projection_id}:v1"],
    )
    store.save_authorization(grant)
    projection = KnowledgeProjection(
        id=projection_id,
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[judgment.id],
        authorization_refs=[grant.id],
        scope_version_refs=[scope.id],
        validity_scope={"domain": "payments"},
        environment_bindings={"runtime": "v1", "model": "m1"},
        counterexample_refs=counterexample_refs,
        metadata={
            "actor_ref": "agent:eua-promoter",
            "resource_ref": projection_id,
            "effect_class": "write-local",
        },
    )
    store.save_knowledge_projection(projection)
    return {
        "claim": claim,
        "judgment": judgment,
        "evidence": evidence,
        "scope": scope,
        "derivation": derivation,
        "grant": grant,
        "projection": projection,
        "challenge": challenge,
    }


def _requirement(seeded: dict[str, object], **overrides: object) -> ExperienceUseRequirement:
    projection = seeded["projection"]
    scope = seeded["scope"]
    assert isinstance(projection, KnowledgeProjection)
    assert isinstance(scope, ChangeObjectRecord)
    values: dict[str, object] = {
        "projection_refs": (projection.id,),
        "use_scope": {"domain": "payments", "task": "refund-review"},
        "subject_version_refs": (scope.id,),
        "environment_bindings": {"runtime": "v1", "model": "m1"},
        "use_context": {"judgment_context": "refund-review"},
    }
    values.update(overrides)
    return ExperienceUseRequirement(**values)  # type: ignore[arg-type]


def test_eua_b_allowed_is_read_only_and_freezes_exact_resolved_graph() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    before = store.export_state()

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "allowed"
    assert admission.allowed is True
    assert store.export_state() == before
    payload = admission.resolved_snapshot.materialize()
    refs = {item["ref"] for item in payload["resolved_objects"]}
    assert seeded["claim"].id in refs  # type: ignore[union-attr]
    assert seeded["evidence"].id in refs  # type: ignore[union-attr]
    assert seeded["judgment"].id in refs  # type: ignore[union-attr]
    assert seeded["grant"].id in refs  # type: ignore[union-attr]
    assert payload["derivations"]
    assert payload["relations"]


def test_eua_001_official_projection_is_not_usable_outside_exact_scope() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(
        _requirement(seeded, use_scope={"domain": "shipping"})
    )
    assert admission.status == "not-applicable"


def test_eua_002_retrieval_hit_does_not_upgrade_candidate_projection() -> None:
    store = InMemoryStateStore()
    projection = KnowledgeProjection(id="retrieved_candidate", lifecycle_status="candidate")
    store.save_knowledge_projection(projection)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(
        ExperienceUseRequirement(
            projection_refs=(projection.id,),
            use_context={"retrieval_score": 1.0},
        )
    )
    assert admission.status == "unavailable"


def test_eua_003_evidence_without_canonical_projection_is_not_usable_experience() -> None:
    store = InMemoryStateStore()
    store.save_record(EvidenceArtifact(id="orphan_evidence", kind="check"))
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(
        ExperienceUseRequirement(projection_refs=("missing_projection",))
    )
    assert admission.status == "unavailable"


def test_eua_004_promotion_authorization_is_provenance_not_action_authority() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))
    assert admission.status == "allowed"
    assert {item.name for item in fields(ExperienceUseAdmission)} == {
        "status",
        "requirement_digest",
        "snapshot_digest",
        "resolved_snapshot",
        "reasons",
    }
    payload = admission.resolved_snapshot.materialize()
    grant_ref = seeded["grant"].id  # type: ignore[union-attr]
    assert grant_ref in {item["ref"] for item in payload["resolved_objects"]}


def test_eua_005_allowed_experience_is_not_permission_to_execute() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))
    assert admission.status == "allowed"
    assert not hasattr(admission, "authorization_ref")
    assert not hasattr(admission, "permit_ref")
    assert not hasattr(admission, "dispatch_ref")


def test_eua_006_scope_match_does_not_hide_environment_or_version_drift() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    evaluator = ExperienceUseAdmissionEvaluator(store)
    env_drift = evaluator.evaluate(
        _requirement(
            seeded,
            environment_bindings={"runtime": "v1", "model": "m2"},
        )
    )
    version_drift = evaluator.evaluate(
        _requirement(seeded, subject_version_refs=("different_scope_version",))
    )
    assert env_drift.status == "stale"
    assert version_drift.status == "stale"


def test_eua_007_same_projection_id_different_semantics_changes_snapshot_digest() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    requirement = _requirement(seeded)
    evaluator = ExperienceUseAdmissionEvaluator(store)
    first = evaluator.evaluate(requirement)
    old_payload = first.resolved_snapshot.materialize()

    claim = seeded["claim"]
    assert isinstance(claim, Assertion)
    store.save_record(claim.model_copy(update={"statement": "revised claim semantics"}))
    second = evaluator.evaluate(requirement)

    assert first.status == second.status == "allowed"
    assert first.requirement_digest == second.requirement_digest
    assert first.snapshot_digest != second.snapshot_digest
    assert old_payload == first.resolved_snapshot.materialize()


def test_eua_008_caller_cannot_omit_canonical_counterexample_from_use_snapshot() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store, counterexample=True)
    requirement = _requirement(seeded)
    assert not hasattr(requirement, "counterexample_refs")

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(requirement)

    assert admission.status == "blocked"
    payload = admission.resolved_snapshot.materialize()
    challenge = seeded["challenge"]
    assert isinstance(challenge, Assertion)
    assert challenge.id in {item["ref"] for item in payload["resolved_objects"]}


def test_eua_009_open_revalidation_relation_blocks_current_use_as_stale() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    projection = seeded["projection"]
    assert isinstance(projection, KnowledgeProjection)
    change = ChangeObjectRecord(id="environment_change", lifecycle_status="draft")
    store.save_record(change)
    store.save_relation(
        RecordRelation(
            id="projection_requires_revalidation",
            relation_type="requires-revalidation",
            subject_ref=projection.id,
            object_ref=change.id,
        )
    )

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "stale"
    assert any(reason.startswith("requires-revalidation:") for reason in admission.reasons)


def test_eua_010_deprecated_or_archived_projection_is_not_usable() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    projection = seeded["projection"]
    assert isinstance(projection, KnowledgeProjection)
    store.save_knowledge_projection(projection.model_copy(update={"lifecycle_status": "deprecated"}))

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "stale"


def test_eua_b_empty_selection_is_not_applicable() -> None:
    store = InMemoryStateStore()
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(ExperienceUseRequirement())
    assert admission.status == "not-applicable"


def test_eua_b_requirement_and_snapshot_are_stable_and_immutable() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    requirement_a = _requirement(seeded)
    requirement_b = ExperienceUseRequirement(
        projection_refs=tuple(reversed(requirement_a.projection_refs)),
        use_scope={"task": "refund-review", "domain": "payments"},
        subject_version_refs=tuple(reversed(requirement_a.subject_version_refs)),
        environment_bindings={"model": "m1", "runtime": "v1"},
        use_context={"judgment_context": "refund-review"},
    )
    evaluator = ExperienceUseAdmissionEvaluator(store)
    first = evaluator.evaluate(requirement_a)
    second = evaluator.evaluate(requirement_b)

    assert first.requirement_digest == second.requirement_digest
    assert first.snapshot_digest == second.snapshot_digest
    with pytest.raises(FrozenInstanceError):
        first.status = "blocked"  # type: ignore[misc]
    payload = first.resolved_snapshot.materialize()
    payload["projections"].clear()
    assert first.snapshot_digest == evaluator.evaluate(requirement_a).snapshot_digest


def test_eua_b_evaluator_requires_only_read_snapshot_surface() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    exported = store.export_state()

    class ExportOnlyStore:
        def __init__(self, state: dict[str, list[dict[str, object]]]) -> None:
            self.state = state
            self.calls = 0

        def export_state(self) -> dict[str, list[dict[str, object]]]:
            self.calls += 1
            return self.state

    read_only = ExportOnlyStore(exported)
    admission = ExperienceUseAdmissionEvaluator(read_only).evaluate(_requirement(seeded))
    assert admission.status == "allowed"
    assert read_only.calls == 1
