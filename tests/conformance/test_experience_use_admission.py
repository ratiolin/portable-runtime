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
    negative_mode: str = "none",
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
    if negative_mode != "none":
        challenge_kwargs: dict[str, object] = {}
        if negative_mode == "outside":
            challenge_kwargs = {
                "scope": {"domain": "shipping"},
                "environment_versions": {"runtime": "v1", "model": "m1"},
                "metadata": {"subject_version_refs": [scope.id]},
            }
        elif negative_mode == "applicable":
            challenge_kwargs = {
                "scope": {"domain": "payments"},
                "environment_versions": {"runtime": "v1", "model": "m1"},
                "metadata": {"subject_version_refs": [scope.id]},
            }
        elif negative_mode != "unknown":
            raise ValueError(f"unsupported negative_mode {negative_mode!r}")

        challenge = Assertion(
            id=f"{projection_id}_counterexample",
            kind="challenge",
            statement="known counterexample",
            lifecycle_status="current",
            epistemic_status="supported",
            **challenge_kwargs,
        )
        store.save_record(challenge)
        counterexample_refs.append(challenge.id)
        if negative_mode in {"applicable", "unknown"}:
            relation_scope = {"domain": "payments"} if negative_mode == "applicable" else None
            relation_metadata = (
                {
                    "subject_version_refs": [scope.id],
                    "environment_bindings": {"runtime": "v1", "model": "m1"},
                }
                if negative_mode == "applicable"
                else {}
            )
            store.save_relation(
                RecordRelation(
                    id=f"{projection_id}_contradiction",
                    relation_type="contradicts",
                    subject_ref=challenge.id,
                    object_ref=claim.id,
                    scope=relation_scope,
                    metadata=relation_metadata,
                )
            )

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


def test_eua_001_official_projection_outside_declared_use_scope_is_blocked() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(
        _requirement(seeded, use_scope={"domain": "shipping"})
    )
    assert admission.status == "blocked"
    assert any(reason.startswith("scope-mismatch:") for reason in admission.reasons)


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
    assert admission.status == "blocked"
    assert any("non-usable-lifecycle" in reason for reason in admission.reasons)


def test_eua_003_evidence_without_canonical_projection_is_unavailable() -> None:
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


def test_eua_007_same_projection_id_new_canonical_fact_changes_snapshot_digest() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    requirement = _requirement(seeded)
    evaluator = ExperienceUseAdmissionEvaluator(store)
    first = evaluator.evaluate(requirement)
    old_payload = first.resolved_snapshot.materialize()
    projection = seeded["projection"]
    assert isinstance(projection, KnowledgeProjection)

    change = ChangeObjectRecord(id="eua_semantic_change", lifecycle_status="draft")
    store.save_record(change)
    store.save_relation(
        RecordRelation(
            id="eua_semantic_revalidation",
            relation_type="requires-revalidation",
            subject_ref=projection.id,
            object_ref=change.id,
        )
    )
    second = evaluator.evaluate(requirement)

    assert first.status == "allowed"
    assert second.status == "stale"
    assert first.requirement_digest == second.requirement_digest
    assert first.snapshot_digest != second.snapshot_digest
    assert old_payload == first.resolved_snapshot.materialize()


def test_eua_008_outside_counterexample_is_visible_but_does_not_block() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store, negative_mode="outside")
    requirement = _requirement(seeded)
    assert not hasattr(requirement, "counterexample_refs")

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(requirement)

    assert admission.status == "allowed"
    payload = admission.resolved_snapshot.materialize()
    challenge = seeded["challenge"]
    assert isinstance(challenge, Assertion)
    assert challenge.id in {item["ref"] for item in payload["resolved_objects"]}
    assert f"negative-fact-outside-use:{challenge.id}" in admission.reasons


def test_eua_b_applicable_counterexample_bound_to_current_assertion_blocks() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store, negative_mode="applicable")

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "blocked"
    challenge = seeded["challenge"]
    assert isinstance(challenge, Assertion)
    assert any(
        reason.startswith("applicable-contradiction:") and reason.endswith(f":{challenge.id}")
        for reason in admission.reasons
    )


def test_eua_b_negative_fact_with_unknown_applicability_fails_closed_unavailable() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store, negative_mode="unknown")

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "unavailable"
    assert any(reason.startswith("negative-applicability-unknown:") for reason in admission.reasons)


def test_eua_b_unresolved_negative_fact_is_unavailable_not_blocked() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    projection = seeded["projection"]
    assert isinstance(projection, KnowledgeProjection)
    store.save_knowledge_projection(
        projection.model_copy(update={"counterexample_refs": ["external:missing-counterexample"]})
    )

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "unavailable"
    assert any(reason.startswith("unresolved:counterexample:") for reason in admission.reasons)


def test_eua_009_open_revalidation_relation_marks_current_use_stale() -> None:
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


def test_eua_010_deprecated_or_archived_projection_is_blocked() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    projection = seeded["projection"]
    assert isinstance(projection, KnowledgeProjection)
    store.save_knowledge_projection(projection.model_copy(update={"lifecycle_status": "deprecated"}))

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seeded))

    assert admission.status == "blocked"


def test_eua_b_empty_selection_alone_is_not_applicable() -> None:
    store = InMemoryStateStore()
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(ExperienceUseRequirement())
    assert admission.status == "not-applicable"
    assert admission.allowed is False


def test_eua_b_projection_refs_are_exact_reliance_set_with_and_semantics() -> None:
    store = InMemoryStateStore()
    allowed_seed = _seed_official(store, projection_id="eua_allowed")
    blocked_seed = _seed_official(
        store,
        projection_id="eua_blocked",
        negative_mode="applicable",
    )
    allowed_projection = allowed_seed["projection"]
    blocked_projection = blocked_seed["projection"]
    allowed_scope = allowed_seed["scope"]
    blocked_scope = blocked_seed["scope"]
    assert isinstance(allowed_projection, KnowledgeProjection)
    assert isinstance(blocked_projection, KnowledgeProjection)
    assert isinstance(allowed_scope, ChangeObjectRecord)
    assert isinstance(blocked_scope, ChangeObjectRecord)

    requirement = ExperienceUseRequirement(
        projection_refs=(allowed_projection.id, blocked_projection.id),
        use_scope={"domain": "payments", "task": "refund-review"},
        subject_version_refs=(allowed_scope.id, blocked_scope.id),
        environment_bindings={"runtime": "v1", "model": "m1"},
        use_context={"judgment_context": "refund-review"},
    )
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(requirement)

    assert admission.status == "blocked"
    payload = admission.resolved_snapshot.materialize()
    assert {item["id"] for item in payload["projections"]} == {
        allowed_projection.id,
        blocked_projection.id,
    }
    assert not hasattr(requirement, "top_k")
    assert not hasattr(requirement, "fallback")
    assert not hasattr(requirement, "retrieval_score")


def test_eua_b_resolved_snapshot_never_substitutes_for_allowed_status() -> None:
    store = InMemoryStateStore()
    seeded = _seed_official(store)
    evaluator = ExperienceUseAdmissionEvaluator(store)

    blocked = evaluator.evaluate(_requirement(seeded, use_scope={"domain": "shipping"}))
    stale = evaluator.evaluate(
        _requirement(seeded, environment_bindings={"runtime": "v1", "model": "m2"})
    )
    unavailable = evaluator.evaluate(
        ExperienceUseRequirement(projection_refs=("missing_projection",))
    )

    assert {blocked.status, stale.status, unavailable.status} == {
        "blocked",
        "stale",
        "unavailable",
    }
    for admission in (blocked, stale, unavailable):
        assert admission.snapshot_digest
        assert admission.resolved_snapshot.materialize()["schema"] == "resolved-experience-use-snapshot-v1"
        assert admission.allowed is False


def test_eua_b_resolved_blocker_is_not_downgraded_to_unavailable_by_another_missing_projection() -> None:
    store = InMemoryStateStore()
    blocked_seed = _seed_official(store, negative_mode="applicable")
    projection = blocked_seed["projection"]
    scope = blocked_seed["scope"]
    assert isinstance(projection, KnowledgeProjection)
    assert isinstance(scope, ChangeObjectRecord)

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(
        ExperienceUseRequirement(
            projection_refs=(projection.id, "missing_projection"),
            use_scope={"domain": "payments"},
            subject_version_refs=(scope.id,),
            environment_bindings={"runtime": "v1", "model": "m1"},
        )
    )

    assert admission.status == "blocked"
    assert any(reason.startswith("projection-unavailable:") for reason in admission.reasons)
    assert any(reason.startswith("applicable-contradiction:") for reason in admission.reasons)


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


def test_eua_b_evaluator_calls_exactly_one_read_snapshot_surface() -> None:
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
