"""Tests for V1.3 Revalidation typed dependency engine — no recursive full-graph invalidation."""

from __future__ import annotations

import random

import pytest

from portable_runtime.records.models import Assertion, EvidenceArtifact, Goal
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.revalidation import (
    assess_revalidation,
    should_block,
)
from portable_runtime.records.revision import apply_revision, create_revision, supersede
from portable_runtime.stores.memory import InMemoryStateStore


def _rand_id(prefix: str = "obj") -> str:
    return f"{prefix}_{random.randint(10000,99999)}"  # noqa: S311

def _make_relation(subject: str, obj: str, rtype: str) -> RecordRelation:
    return RecordRelation(subject_ref=subject, object_ref=obj, relation_type=rtype)  # type: ignore[arg-type]

def test_assess_revalidation_direct_matching():
    # evaluator change should only affect validated-under / evaluated-by
    rel_valid = _make_relation("assertion_1", "evaluator_v8", "validated-under")
    rel_eval = _make_relation("assertion_2", "evaluator_v8", "evaluated-by")
    rel_other = _make_relation("artifact_1", "evaluator_v8", "executed-with")  # not in evaluator watch
    rel_unrelated = _make_relation("assertion_3", "evaluator_v7", "validated-under")
    rel_depends = _make_relation("goal_1", "evaluator_v8", "depends-on")  # not in evaluator watch either

    result = assess_revalidation("evaluator_v8", "evaluator", [rel_valid, rel_eval, rel_other, rel_unrelated, rel_depends])
    affected_ids = {r.affected_ref for r in result}
    assert "assertion_1" in affected_ids
    assert "assertion_2" in affected_ids
    assert "artifact_1" not in affected_ids, "executed-with should not be affected by evaluator change"
    assert "assertion_3" not in affected_ids
    assert "goal_1" not in affected_ids
    assert len(result) == 2

    # check required_action for evaluator validated-under should be block-next-use
    for a in result:
        assert a.required_action == "block-next-use"
        assert a.severity == "high"
        assert should_block(a) is True


def test_assess_revalidation_no_recursive_pollution():
    # A -> depends-on B, B -> depends-on C, change C should only affect B direct, not A transitive
    rel_b_c = _make_relation("record_B", "change_X", "depends-on")
    rel_a_b = _make_relation("record_A", "record_B", "depends-on")
    result = assess_revalidation("change_X", "model", [rel_b_c, rel_a_b])
    affected = {r.affected_ref for r in result}
    assert "record_B" in affected
    assert "record_A" not in affected, "must not recursively invalidate transitive dependents"


def test_assess_revalidation_all_change_types():
    watch_map = {
        "evaluator": {"validated-under", "evaluated-by"},
        "model": {"validated-under", "evaluated-by", "depends-on"},
        "code": {"executed-with", "validated-under", "depends-on"},
        "dataset": {"measured-by", "depends-on"},
        "permission": {"authorized-under", "depends-on"},
        "classification": {"scoped-to", "depends-on"},
        "state_space": {"scoped-to", "depends-on", "validated-under"},
        "environment": {"validated-under", "executed-with", "measured-by", "depends-on"},
    }
    for ct, watch in watch_map.items():
        # create one relation per possible type
        all_types = ["validated-under","evaluated-by","executed-with","measured-by","authorized-under","scoped-to","depends-on","supports","produces"]
        rels = [_make_relation(f"subj_{t}", "change_1", t) for t in all_types]
        result = assess_revalidation("change_1", ct, rels)
        result_types = set()
        # map affected back via reason_refs -> need to recover rt; instead check count matches watch
        # we stored reason_refs as relation ids, but we can infer by checking affected_ref prefix
        # simpler: count must equal len(watch)
        assert len(result) == len(watch), f"change_type {ct} expected {len(watch)} but got {len(result)} Types {watch}"
        for a in result:
            assert a.required_action in {"none","warn","background-revalidate","block-next-use","require-human-review","reopen"}
            assert a.impact_type == "warn"
            assert a.revalidation_disposition is not None
            assert a.required_action == a.revalidation_disposition.action
            assert a.severity in {"low","medium","high","critical"}


def test_assess_revalidation_permission_and_classification():
    rel_auth = _make_relation("action_1", "perm_v1", "authorized-under")
    rel_scope = _make_relation("policy_1", "class_v1", "scoped-to")
    r1 = assess_revalidation("perm_v1", "permission", [rel_auth, rel_scope])
    assert len(r1) == 1 and r1[0].affected_ref == "action_1"
    assert r1[0].required_action == "require-human-review"

    r2 = assess_revalidation("class_v1", "classification", [rel_auth, rel_scope])
    assert len(r2) == 1 and r2[0].affected_ref == "policy_1"
    assert r2[0].required_action == "require-human-review"


def test_assess_revalidation_state_space_reopen():
    rel_scope = _make_relation("goal_1", "state_v1", "scoped-to")
    result = assess_revalidation("state_v1", "state_space", [rel_scope])
    assert result[0].required_action == "reopen"
    assert result[0].severity == "critical"
    assert should_block(result[0]) is True


def test_assess_invalid_change_ref_raises():
    with pytest.raises(ValueError):
        assess_revalidation("", "model", [])


def test_property_random_graph_no_full_pollution():
    """Property: random legal Record Graph -> random bump -> only typed dependencies affected."""
    for _ in range(50):
        random.seed()  # use system random
        # generate 10-20 records
        records = []
        for i in range(random.randint(10, 20)):
            rt = random.choice(["Assertion","EvidenceArtifact","Goal","Constraint","Policy"])
            # use BaseRecord for simplicity with lifecycle checks bypass? Use actual models
            if rt == "Assertion":
                records.append(Assertion(statement=f"stmt {i}", lifecycle_status="draft"))
            elif rt == "EvidenceArtifact":
                records.append(EvidenceArtifact(uri=f"file://{i}", lifecycle_status="current"))
            else:
                records.append(Goal(direction=f"dir {i}", lifecycle_status="proposed"))

        record_ids = [r.id for r in records]
        # pick a change_ref that is an environment / evaluator version identifier
        change_ref = f"env_{random.randint(1,100)}"
        # generate 30 random relations, some point to change_ref, some not
        relation_types = ["validated-under","evaluated-by","executed-with","measured-by","authorized-under","scoped-to","depends-on","supports","produces","revises","supersedes"]
        relations: list[RecordRelation] = []
        target_typed_subjects: set[str] = set()
        for _ in range(30):
            subj = random.choice(record_ids)
            # 40% point to change_ref, 60% random other
            if random.random() < 0.4:
                obj = change_ref
                rt = random.choice(relation_types)
                # count if this rt would be in environment watch set
                env_watch = {"validated-under","executed-with","measured-by","depends-on"}
                if rt in env_watch:
                    target_typed_subjects.add(subj)
            else:
                obj = _rand_id("other")
                rt = random.choice(relation_types)
            try:
                rel = RecordRelation(subject_ref=subj, object_ref=obj, relation_type=rt)  # type: ignore[arg-type]
            except Exception:
                continue
            relations.append(rel)

        result = assess_revalidation(change_ref, "environment", relations)
        # must equal direct typed matches only
        assert len(result) == len(target_typed_subjects), f"expected {len(target_typed_subjects)} typed matches, got {len(result)}"
        # ensure not full graph polluted: affected set size <= record count and strictly less than total relations when not all match
        assert len(result) <= len(record_ids)
        # verify no transitive leakage: all affected_ref must be direct subjects of matching relations
        direct_subjects = {r.subject_ref for r in relations if r.object_ref == change_ref and r.relation_type in {"validated-under","executed-with","measured-by","depends-on"}}
        assert {a.affected_ref for a in result} == direct_subjects
        # also verify severity and required_action validity
        for a in result:
            assert a.change_ref == change_ref
            assert a.required_action in {"none","warn","background-revalidate","block-next-use","require-human-review","reopen"}
            assert a.reason_refs  # at least one reason


def test_revision_create_and_apply_and_supersede():
    store = InMemoryStateStore()
    old = Assertion(statement="old claim", lifecycle_status="current")
    new = Assertion(statement="new claim", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)

    rev = create_revision(old.id, new.id, created_by="tester")
    assert rev.revises_ref == old.id
    assert rev.produces_ref == new.id
    assert rev.lifecycle_status == "proposed"
    assert old.id != new.id

    # apply
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:revision",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[rev.id],
    )
    store.save_authorization(grant)
    apply_revision(rev, store=store, authorization_ref=grant.id, actor_ref="agent:revision", resource_ref=old.id)
    assert rev.lifecycle_status == "applied"
    # persisted
    fetched = store.get_record(rev.id)
    assert fetched is not None
    assert fetched.lifecycle_status == "applied"

    # supersede
    rel = supersede(old.id, new.id, store=store, revision=rev)
    assert rel.relation_type == "supersedes"
    assert rel.subject_ref == new.id
    assert rel.object_ref == old.id

    old_fetched = store.get_record(old.id)
    assert old_fetched is not None
    assert old_fetched.lifecycle_status == "superseded"
    # new remains
    new_fetched = store.get_record(new.id)
    assert new_fetched is not None
    assert new_fetched.id == new.id
    # old not deleted
    assert store.get_record(old.id) is not None
    # relation persisted
    assert store.get_relation(rel.id) is not None


def test_revision_no_silent_overwrite():
    store = InMemoryStateStore()
    old = EvidenceArtifact(uri="file://old", lifecycle_status="current")
    new = EvidenceArtifact(uri="file://new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    rev = create_revision(old, new)  # pass objects directly
    store.save_record(rev)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:revision",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[rev.id],
    )
    store.save_authorization(grant)
    apply_revision(rev, store=store, authorization_ref=grant.id, actor_ref="agent:revision", resource_ref=old.id)
    supersede(store, old.id, new.id, revision=rev)
    # both still present - old retained, not silently overwritten
    assert len(store.list_records()) >= 3
    ids = {r.id for r in store.list_records()}
    assert old.id in ids and new.id in ids and rev.id in ids
    assert store.get_record(rev.id) is not None


def test_revision_self_ref_rejected():
    with pytest.raises(ValueError):
        create_revision("same_id", "same_id")


def test_stores_persist_revision_changeobject():
    # ensure save_record works for Revision and ChangeObject types via sqlite path as well
    import tempfile
    from pathlib import Path

    from portable_runtime.records.models import ChangeObjectRecord
    from portable_runtime.stores.sqlite import SQLiteStateStore

    store = InMemoryStateStore()
    rev = create_revision("old_v1", "new_v2")
    store.save_record(rev)
    assert store.get_record(rev.id) is not None

    co = ChangeObjectRecord(object_type="model", lifecycle_status="draft")
    store.save_record(co)
    assert store.get_record(co.id) is not None

    # sqlite variant
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / "test.db"
        sstore = SQLiteStateStore(dbp)
        sstore.save_record(rev)
        sstore.save_record(co)
        assert sstore.get_record(rev.id) is not None
        assert sstore.get_record(co.id) is not None
        sstore.close()


def test_required_action_values():
    # all required actions enumerated must be reachable via some change_type+relation
    all_actions = set()
    for ct in ["evaluator","model","code","dataset","permission","classification","state_space","environment"]:
        watch = {
            "evaluator": ["validated-under"],
            "model": ["depends-on"],
            "code": ["executed-with"],
            "dataset": ["measured-by"],
            "permission": ["authorized-under"],
            "classification": ["scoped-to"],
            "state_space": ["scoped-to"],
            "environment": ["validated-under"],
        }[ct]
        for rt in watch:
            rel = _make_relation("subj", "chg", rt)
            res = assess_revalidation("chg", ct, [rel])
            assert len(res) == 1
            all_actions.add(res[0].required_action)
    assert "block-next-use" in all_actions
    assert "require-human-review" in all_actions
    assert "reopen" in all_actions
    assert "background-revalidate" in all_actions
