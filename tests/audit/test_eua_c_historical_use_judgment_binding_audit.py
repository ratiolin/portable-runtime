"""EUA-C audit: historical Experience Use must bind an exact judgment.

Audit-only. These tests freeze current evidence and missing responsibilities;
they do not define a production persistence API.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from portable_runtime.experience.use_admission import ExperienceUseAdmission
from portable_runtime.protocol.validation import _iter_ref_edges
from portable_runtime.records import models as record_models
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, DecisionRecord, Derivation
from portable_runtime.records.relations import RecordRelation, RelationType
from portable_runtime.stores.memory import InMemoryStateStore


def test_eua_c_001_existing_assertion_is_structurally_sufficient_as_domain_judgment_carrier() -> None:
    fields = set(Assertion.model_fields)
    assert {
        "id",
        "version",
        "statement",
        "epistemic_status",
        "lifecycle_status",
        "scope",
        "source_refs",
        "environment_versions",
        "known_limitations",
        "invalidation_conditions",
        "metadata",
    } <= fields
    assert not hasattr(record_models, "DomainJudgment")


def test_eua_c_002_projection_internal_judgment_is_not_a_historical_use_field() -> None:
    assert "epistemic_judgment_refs" in KnowledgeProjection.model_fields
    admission_fields = set(ExperienceUseAdmission.__dataclass_fields__)
    assert "judgment_ref" not in admission_fields
    assert "historical_use_ref" not in admission_fields


def test_eua_c_003_derivation_does_not_bind_exact_experience_admission_semantics() -> None:
    fields = set(Derivation.model_fields)
    assert {"premise_refs", "evidence_refs", "conclusion_ref"} <= fields
    assert "requirement_digest" not in fields
    assert "snapshot_digest" not in fields
    assert "resolved_snapshot" not in fields

    edge_source = inspect.getsource(_iter_ref_edges)
    assert 'record_type == "Derivation"' not in edge_source


def test_eua_c_004_generic_relation_is_append_only_but_has_no_historical_reliance_contract() -> None:
    relation_types = set(RelationType.__args__)  # type: ignore[attr-defined]
    assert "relied-on" not in relation_types
    assert "experience-relied-on" not in relation_types
    assert "metadata" in RecordRelation.model_fields

    save_relation_source = inspect.getsource(InMemoryStateStore.save_relation)
    assert "append-only" in save_relation_source
    assert "snapshot_digest" not in save_relation_source
    assert "requirement_digest" not in save_relation_source
    assert "ExperienceUseAdmission" not in save_relation_source


def test_eua_c_005_responsibility_decision_citation_cannot_name_exact_experience_snapshot() -> None:
    fields = set(DecisionRecord.model_fields)
    assert "rationale_refs" in fields
    assert "snapshot_digest" not in fields
    assert "experience_use_ref" not in fields
    assert "resolved_snapshot" not in fields


def test_eua_c_006_no_store_owned_historical_experience_use_commit_exists() -> None:
    source = inspect.getsource(InMemoryStateStore)
    assert "commit_historical_experience_use" not in source
    assert "commit_experience_use" not in source
    assert "historical_experience_use" not in source


def test_eua_c_007_no_durable_historical_experience_use_authority_type_exists() -> None:
    root = Path("src/portable_runtime")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "class HistoricalExperienceUseBinding" not in source
    assert "class DomainJudgment" not in source


def test_eua_c_008_eua_b_snapshot_remains_ephemeral_not_a_store_bucket() -> None:
    store = InMemoryStateStore()
    state = store.export_state()
    assert "experience_use" not in state
    assert "experience_use_snapshot" not in state
    assert "historical_experience_use" not in state


_HUB_COUNTEREXAMPLES = [
    (
        "HUB-001",
        "allowed ExperienceUseAdmission without a task/domain judgment is not historical experience use",
    ),
    (
        "HUB-002",
        "the same snapshot used by J1 does not prove use by a different judgment J2",
    ),
    (
        "HUB-003",
        "the same exact judgment identity cannot be rebound to different snapshot semantics",
    ),
    (
        "HUB-004",
        "projection-internal epistemic_judgment_refs are not the task/domain judgment consuming experience",
    ),
    (
        "HUB-005",
        "a Responsibility Decision citing a projection does not prove its preceding judgment used the exact snapshot",
    ),
    (
        "HUB-006",
        "later projection or revalidation drift must not mutate a historical experience-use fact",
    ),
    (
        "HUB-007",
        "a standalone durable evaluator snapshot optionally linked later is not an atomic historical reliance fact",
    ),
    (
        "HUB-008",
        "current projection state cannot backfill a missing historical experience-use binding",
    ),
]


@pytest.mark.parametrize(
    ("case_id", "obligation"),
    _HUB_COUNTEREXAMPLES,
    ids=[item[0] for item in _HUB_COUNTEREXAMPLES],
)
@pytest.mark.xfail(strict=True, reason="EUA-C audit freeze; durable historical-use authority not implemented")
def test_eua_c_counterexamples_require_future_store_owned_historical_binding(
    case_id: str,
    obligation: str,
) -> None:
    raise AssertionError(f"{case_id}: {obligation}")
