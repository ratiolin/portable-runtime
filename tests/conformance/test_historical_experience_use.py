from __future__ import annotations

import threading
from dataclasses import fields
from typing import Any, Iterator

import pytest

from portable_runtime.core.models import Event
from portable_runtime.experience.historical_use import (
    DOMAIN_JUDGMENT_SEMANTIC_ROLE,
    HISTORICAL_EXPERIENCE_USE_EVENT_TYPE,
    HistoricalExperienceUse,
    HistoricalExperienceUseCommitRequest,
    assert_historical_experience_use_import_closed,
    historical_experience_use_event_id,
    historical_experience_use_from_event,
    validate_historical_experience_use_authority_graph,
)
from portable_runtime.experience.use_admission import (
    EXPERIENCE_USE_ADMISSION_CONTRACT_VERSION,
    ExperienceUseAdmissionEvaluator,
    ExperienceUseRequirement,
)
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, ChangeObjectRecord, Derivation, EvidenceArtifact
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _seed_official(store: Any, *, projection_id: str = "hist_projection") -> dict[str, object]:
    claim = Assertion(
        id=f"{projection_id}_claim",
        statement="settled experience claim",
        lifecycle_status="current",
        epistemic_status="supported",
    )
    epistemic_judgment = Assertion(
        id=f"{projection_id}_epistemic_judgment",
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
        premise_refs=[epistemic_judgment.id],
        evidence_refs=[evidence.id],
        conclusion_ref=claim.id,
        metadata={"scope_version_refs": [scope.id]},
        lifecycle_status="current",
    )
    for record in (claim, epistemic_judgment, evidence, scope, derivation):
        store.save_record(record)
    store.save_relation(
        RecordRelation(
            id=f"{projection_id}_derived",
            relation_type="derived-from",
            subject_ref=claim.id,
            object_ref=epistemic_judgment.id,
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
    grant = create_grant_for_approval(
        principal_ref="human:experience-owner",
        grantee_ref="agent:experience-promoter",
        allowed_capabilities=["knowledge.promote"],
        subject_version_refs=[projection_id, f"{projection_id}:v1"],
    )
    store.save_authorization(grant)
    projection = KnowledgeProjection(
        id=projection_id,
        lifecycle_status="official",
        current_assertion_refs=[claim.id],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=[epistemic_judgment.id],
        authorization_refs=[grant.id],
        scope_version_refs=[scope.id],
        validity_scope={"domain": "payments"},
        environment_bindings={"runtime": "v1", "model": "m1"},
        metadata={
            "actor_ref": "agent:experience-promoter",
            "resource_ref": projection_id,
            "effect_class": "write-local",
        },
    )
    store.save_knowledge_projection(projection)
    return {
        "claim": claim,
        "epistemic_judgment": epistemic_judgment,
        "scope": scope,
        "projection": projection,
    }


def _requirement(seed: dict[str, object]) -> ExperienceUseRequirement:
    projection = seed["projection"]
    scope = seed["scope"]
    assert isinstance(projection, KnowledgeProjection)
    assert isinstance(scope, ChangeObjectRecord)
    return ExperienceUseRequirement(
        projection_refs=(projection.id,),
        use_scope={"domain": "payments", "task": "refund-review"},
        subject_version_refs=(scope.id,),
        environment_bindings={"runtime": "v1", "model": "m1"},
        use_context={"judgment_context": "refund-review"},
    )


def _task_judgment(
    judgment_id: str = "task_domain_judgment",
    *,
    epistemic_status: str = "unverified",
) -> Assertion:
    return Assertion(
        id=judgment_id,
        statement="refund should be reviewed under the selected operational hypothesis",
        lifecycle_status="current",
        epistemic_status=epistemic_status,  # type: ignore[arg-type]
        version=1,
        metadata={"semantic_role": DOMAIN_JUDGMENT_SEMANTIC_ROLE},
    )


def _request(store: Any, seed: dict[str, object], judgment: Assertion | None = None) -> HistoricalExperienceUseCommitRequest:
    requirement = _requirement(seed)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(requirement)
    assert admission.status == "allowed"
    return HistoricalExperienceUseCommitRequest(
        judgment=judgment or _task_judgment(),
        requirement=requirement,
        expected_requirement_digest=admission.requirement_digest,
        expected_snapshot_digest=admission.snapshot_digest,
        expected_admission_contract_version=admission.admission_contract_version,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path) -> Iterator[Any]:
    if request.param == "memory":
        value: Any = InMemoryStateStore()
    else:
        value = SQLiteStateStore(tmp_path / "historical-experience-use.db")
    try:
        yield value
    finally:
        if isinstance(value, SQLiteStateStore):
            value.close()


def test_eua_d_admission_contract_is_explicit_and_not_snapshot_schema(store: Any) -> None:
    seed = _seed_official(store)
    admission = ExperienceUseAdmissionEvaluator(store).evaluate(_requirement(seed))
    assert admission.admission_contract_version == EXPERIENCE_USE_ADMISSION_CONTRACT_VERSION
    assert admission.admission_contract_version == "experience-use-admission-v1"
    assert admission.resolved_snapshot.materialize()["schema"] == "resolved-experience-use-snapshot-v1"
    assert admission.admission_contract_version != admission.resolved_snapshot.materialize()["schema"]


def test_eua_d_commit_request_cannot_submit_resolved_authority_payload() -> None:
    names = {field.name for field in fields(HistoricalExperienceUseCommitRequest)}
    assert names == {
        "judgment",
        "requirement",
        "expected_requirement_digest",
        "expected_snapshot_digest",
        "expected_admission_contract_version",
    }
    forbidden = {
        "historical_binding",
        "resolved_snapshot",
        "snapshot_semantic_json",
        "assertion_refs",
        "evidence_refs",
        "counterexample_refs",
    }
    assert not (names & forbidden)


def test_hub_001_new_judgment_and_exact_allowed_snapshot_commit_atomically(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)

    binding = store.commit_historical_experience_use(request)

    assert isinstance(binding, HistoricalExperienceUse)
    assert binding.judgment_ref == request.judgment.id
    assert binding.judgment_version == request.judgment.version
    assert binding.requirement_digest == request.expected_requirement_digest
    assert binding.snapshot_digest == request.expected_snapshot_digest
    assert binding.admission_contract_version == EXPERIENCE_USE_ADMISSION_CONTRACT_VERSION
    persisted_judgment = store.get_record(request.judgment.id)
    assert isinstance(persisted_judgment, Assertion)
    event = store.get_event(binding.id)
    assert event is not None
    assert historical_experience_use_from_event(event) == binding
    assert "historical_experience_use" not in store.export_state()


def test_hub_002_same_snapshot_does_not_transfer_between_judgments(store: Any) -> None:
    seed = _seed_official(store)
    first = _request(store, seed, _task_judgment("judgment_j1"))
    second = _request(store, seed, _task_judgment("judgment_j2"))

    binding1 = store.commit_historical_experience_use(first)
    assert store.get_event(historical_experience_use_event_id(second.judgment.id, 1)) is None
    binding2 = store.commit_historical_experience_use(second)

    assert binding1.id != binding2.id
    assert binding1.snapshot_digest == binding2.snapshot_digest
    assert binding1.judgment_ref != binding2.judgment_ref


def test_hub_003_same_exact_judgment_same_semantics_replays(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    first = store.commit_historical_experience_use(request)
    second = store.commit_historical_experience_use(request)
    assert second == first
    matching = [event for event in store.list_events(request.judgment.id) if event.type == HISTORICAL_EXPERIENCE_USE_EVENT_TYPE]
    assert len(matching) == 1


def test_hub_003_same_exact_judgment_changed_snapshot_rebounds(store: Any) -> None:
    seed = _seed_official(store)
    original = _request(store, seed)
    store.commit_historical_experience_use(original)
    projection = seed["projection"]
    assert isinstance(projection, KnowledgeProjection)
    change = ChangeObjectRecord(id="later_semantic_change", lifecycle_status="draft")
    store.save_record(change)
    store.save_relation(
        RecordRelation(
            id="later_requires_revalidation",
            relation_type="requires-revalidation",
            subject_ref=projection.id,
            object_ref=change.id,
        )
    )
    later = ExperienceUseAdmissionEvaluator(store).evaluate(original.requirement)
    assert later.snapshot_digest != original.expected_snapshot_digest
    rebound = HistoricalExperienceUseCommitRequest(
        judgment=original.judgment,
        requirement=original.requirement,
        expected_requirement_digest=later.requirement_digest,
        expected_snapshot_digest=later.snapshot_digest,
        expected_admission_contract_version=later.admission_contract_version,
    )
    with pytest.raises(ValueError, match="snapshot rebound"):
        store.commit_historical_experience_use(rebound)


def test_hub_004_projection_qualifying_judgment_cannot_be_consuming_judgment(store: Any) -> None:
    seed = _seed_official(store)
    qualifying = seed["epistemic_judgment"]
    assert isinstance(qualifying, Assertion)
    consuming_shape = qualifying.model_copy(
        update={"metadata": {**qualifying.metadata, "semantic_role": DOMAIN_JUDGMENT_SEMANTIC_ROLE}}
    )
    request = _request(store, seed, consuming_shape)
    with pytest.raises(ValueError, match="qualifies selected experience|backfill"):
        store.commit_historical_experience_use(request)


def test_hub_004_projection_current_assertion_cannot_be_consuming_judgment(store: Any) -> None:
    seed = _seed_official(store)
    claim = seed["claim"]
    assert isinstance(claim, Assertion)
    consuming_shape = claim.model_copy(
        update={"metadata": {**claim.metadata, "semantic_role": DOMAIN_JUDGMENT_SEMANTIC_ROLE}}
    )
    request = _request(store, seed, consuming_shape)
    with pytest.raises(ValueError, match="qualifies selected experience|backfill"):
        store.commit_historical_experience_use(request)


def test_eua_d_allowed_experience_does_not_upgrade_judgment_truth(store: Any) -> None:
    seed = _seed_official(store)
    judgment = _task_judgment(epistemic_status="contested")
    request = _request(store, seed, judgment)
    store.commit_historical_experience_use(request)
    persisted = store.get_record(judgment.id)
    assert isinstance(persisted, Assertion)
    assert persisted.epistemic_status == "contested"


def test_hub_006_later_projection_drift_does_not_mutate_or_invalidate_historical_replay(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    binding = store.commit_historical_experience_use(request)
    original_json = binding.snapshot_semantic_json
    projection = seed["projection"]
    assert isinstance(projection, KnowledgeProjection)
    change = ChangeObjectRecord(id="post_commit_change", lifecycle_status="draft")
    store.save_record(change)
    store.save_relation(
        RecordRelation(
            id="post_commit_revalidation",
            relation_type="requires-revalidation",
            subject_ref=projection.id,
            object_ref=change.id,
        )
    )
    assert ExperienceUseAdmissionEvaluator(store).evaluate(request.requirement).status == "stale"
    replay = store.commit_historical_experience_use(request)
    assert replay == binding
    assert replay.snapshot_semantic_json == original_json


def test_hub_007_state_change_between_caller_evaluation_and_commit_fails_compare_and_bind(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    projection = seed["projection"]
    assert isinstance(projection, KnowledgeProjection)
    change = ChangeObjectRecord(id="toctou_change", lifecycle_status="draft")
    store.save_record(change)
    store.save_relation(
        RecordRelation(
            id="toctou_requires_revalidation",
            relation_type="requires-revalidation",
            subject_ref=projection.id,
            object_ref=change.id,
        )
    )

    with pytest.raises(ValueError, match="requires allowed admission|snapshot changed"):
        store.commit_historical_experience_use(request)

    assert store.get_record(request.judgment.id) is None
    assert store.get_event(historical_experience_use_event_id(request.judgment.id, 1)) is None


def test_hub_008_existing_unbound_judgment_cannot_be_backfilled(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    store.save_record(request.judgment)

    with pytest.raises(ValueError, match="retroactive.*backfill"):
        store.commit_historical_experience_use(request)

    assert store.get_event(historical_experience_use_event_id(request.judgment.id, 1)) is None


def test_eua_d_full_record_validation_is_not_bypassed(store: Any) -> None:
    seed = _seed_official(store)
    invalid = _task_judgment().model_copy(update={"undeclared_historical_field": "forbidden"})
    request = _request(store, seed, invalid)
    with pytest.raises(ValueError, match="undeclared fields"):
        store.commit_historical_experience_use(request)
    assert store.get_record(invalid.id) is None


def test_eua_d_direct_authority_event_append_is_closed(store: Any) -> None:
    forged = Event(
        id=historical_experience_use_event_id("forged_judgment", 1),
        type=HISTORICAL_EXPERIENCE_USE_EVENT_TYPE,
        subject_ref="forged_judgment",
        payload={},
    )
    with pytest.raises(ValueError, match="commit_historical_experience_use"):
        store.append_event(forged)


def test_eua_d_generic_import_of_historical_authority_is_closed(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    store.commit_historical_experience_use(request)
    exported = store.export_state()
    with pytest.raises(ValueError, match="import/backfill is closed"):
        assert_historical_experience_use_import_closed(exported)


def test_eua_d_memory_and_sqlite_import_paths_reject_historical_authority(store: Any, tmp_path) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    store.commit_historical_experience_use(request)
    exported = store.export_state()

    memory_target = InMemoryStateStore()
    with pytest.raises(ValueError, match="import/backfill is closed"):
        memory_target.import_state(exported)

    sqlite_target = SQLiteStateStore(tmp_path / "import-target.db")
    try:
        with pytest.raises(ValueError, match="import/backfill is closed"):
            sqlite_target.import_state(exported)
    finally:
        sqlite_target.close()


def test_eua_d_fault_after_judgment_write_before_event_rolls_back(store: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)

    def fail_before_event(_event: Event) -> None:
        raise RuntimeError("injected-before-event")

    monkeypatch.setattr(store, "append_event", fail_before_event)
    with pytest.raises(RuntimeError, match="injected-before-event"):
        store.commit_historical_experience_use(request)

    assert store.get_record(request.judgment.id) is None
    assert store.get_event(historical_experience_use_event_id(request.judgment.id, 1)) is None


def test_eua_d_fault_after_event_write_before_commit_rolls_back_both(store: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    original_append = store.append_event

    def fail_after_event(event: Event) -> None:
        original_append(event)
        raise RuntimeError("injected-after-event")

    monkeypatch.setattr(store, "append_event", fail_after_event)
    with pytest.raises(RuntimeError, match="injected-after-event"):
        store.commit_historical_experience_use(request)

    assert store.get_record(request.judgment.id) is None
    assert store.get_event(historical_experience_use_event_id(request.judgment.id, 1)) is None


def test_eua_d_two_concurrent_same_judgment_commits_linearize_one_semantic_result(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    results: list[HistoricalExperienceUse] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(store.commit_historical_experience_use(request))
        except BaseException as exc:  # pragma: no cover - diagnostic path
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert len(results) == 2
    assert results[0] == results[1]
    matching = [event for event in store.list_events(request.judgment.id) if event.type == HISTORICAL_EXPERIENCE_USE_EVENT_TYPE]
    assert len(matching) == 1


def test_eua_d_binding_without_judgment_is_invalid_authority_graph() -> None:
    semantic_json = (
        '{"derivations":[],"projections":[],"relations":[],"requirement":'
        '{"environment_bindings":{},"projection_refs":[],"schema":"experience-use-requirement-v1",'
        '"subject_version_refs":[],"use_context":{},"use_scope":{}},'
        '"resolved_objects":[],"schema":"resolved-experience-use-snapshot-v1","unresolved":[]}'
    )
    import hashlib
    import json

    requirement_payload = json.loads(semantic_json)["requirement"]
    requirement_digest = hashlib.sha256(
        json.dumps(requirement_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot_digest = hashlib.sha256(semantic_json.encode()).hexdigest()
    event = Event(
        id=historical_experience_use_event_id("missing_judgment", 1),
        type=HISTORICAL_EXPERIENCE_USE_EVENT_TYPE,
        subject_ref="missing_judgment",
        payload={
            "schema": "historical-experience-use-v1",
            "semantic_role": "historical-experience-use",
            "judgment_ref": "missing_judgment",
            "judgment_version": 1,
            "requirement_digest": requirement_digest,
            "snapshot_digest": snapshot_digest,
            "snapshot_semantic_json": semantic_json,
            "selected_projection_refs": [],
            "admission_contract_version": EXPERIENCE_USE_ADMISSION_CONTRACT_VERSION,
        },
    )
    with pytest.raises(ValueError, match="judgment missing"):
        validate_historical_experience_use_authority_graph(
            {"record": [], "event": [event.model_dump(mode="json")]}
        )


def test_eua_d_contract_drift_fails_before_new_authority(store: Any) -> None:
    seed = _seed_official(store)
    request = _request(store, seed)
    drifted = HistoricalExperienceUseCommitRequest(
        judgment=request.judgment,
        requirement=request.requirement,
        expected_requirement_digest=request.expected_requirement_digest,
        expected_snapshot_digest=request.expected_snapshot_digest,
        expected_admission_contract_version="experience-use-admission-v2",
    )
    with pytest.raises(ValueError, match="contract changed"):
        store.commit_historical_experience_use(drifted)
    assert store.get_record(request.judgment.id) is None
