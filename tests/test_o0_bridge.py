from datetime import UTC, datetime, timedelta

from portable_runtime.observation.o0 import (
    FormalDependencyInput,
    FormalEvidenceInput,
    FormalHistoricalTraceInput,
    FormalImpactInput,
    FormalObservationBundle0,
    FormalOperativeStatusInput,
    FormalRequirementInput,
    FormalReviewInput,
    O0ComparisonCase,
    O0Snapshot,
    RuntimeObservationBundle0,
    alpha_f0,
    alpha_r0,
    discover_b0,
)
from portable_runtime.records.authorization import AuthorizationGrant
from portable_runtime.records.models import Assertion, RevisionRecord
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.revalidation import (
    AffectedAssessment,
    DependencyImpact,
    RevalidationDisposition,
)

T0 = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)


def _family(snapshot: O0Snapshot, family: str):
    return [observation for observation in snapshot.observations if observation.family == family]


def _impact_and_assessment() -> tuple[DependencyImpact, AffectedAssessment]:
    impact = DependencyImpact(
        change_ref="change-1",
        affected_ref="runtime-subject",
        relation_type="depends-on",
        reason_refs=["relation-1"],
    )
    assessment = AffectedAssessment(
        change_ref="change-1",
        affected_ref="runtime-subject",
        reason_refs=["relation-1"],
        dependency_impact=impact,
        revalidation_disposition=RevalidationDisposition(
            action="require-human-review",
            policy_ref="policy-1",
            rationale_refs=["relation-1"],
        ),
    )
    return impact, assessment


def _f1_cases() -> list[O0ComparisonCase]:
    before = Assertion(
        id="runtime-subject",
        statement="candidate conclusion",
        epistemic_status="supported",
        lifecycle_status="current",
    )
    after = before.model_copy(update={"epistemic_status": "revalidation-required"})

    runtime_before = alpha_r0(RuntimeObservationBundle0(observed_at=T0, records=[before]))
    runtime_after = alpha_r0(RuntimeObservationBundle0(observed_at=T0, records=[after]))

    formal_before = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            historical_traces=[
                FormalHistoricalTraceInput(subject_ref="formal-subject", trace_kind="warrant")
            ],
            operative_statuses=[
                FormalOperativeStatusInput(
                    subject_ref="formal-subject",
                    layer="warrant.usable",
                    status="qualified",
                )
            ],
        )
    )
    formal_after = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            historical_traces=[
                FormalHistoricalTraceInput(subject_ref="formal-subject", trace_kind="warrant")
            ],
            operative_statuses=[
                FormalOperativeStatusInput(
                    subject_ref="formal-subject",
                    layer="warrant.usable",
                    status="withdrawn",
                )
            ],
        )
    )

    mapping = {"runtime-subject": "formal-subject"}
    return [
        O0ComparisonCase(runtime=runtime_before, formal=formal_before, runtime_to_formal_ids=mapping),
        O0ComparisonCase(runtime=runtime_after, formal=formal_after, runtime_to_formal_ids=mapping),
    ]


def test_f1_historical_trace_retained_while_operative_status_changes() -> None:
    cases = _f1_cases()
    runtime_before = cases[0].runtime
    runtime_after = cases[1].runtime
    formal_before = cases[0].formal
    formal_after = cases[1].formal

    runtime_trace_before = _family(runtime_before, "historicalTrace")
    runtime_trace_after = _family(runtime_after, "historicalTrace")
    formal_trace_before = _family(formal_before, "historicalTrace")
    formal_trace_after = _family(formal_after, "historicalTrace")

    assert [(item.subject_ref, item.bridge_value) for item in runtime_trace_before] == [
        ("runtime-subject", "present")
    ]
    assert [(item.subject_ref, item.bridge_value) for item in runtime_trace_after] == [
        ("runtime-subject", "present")
    ]
    assert [(item.subject_ref, item.bridge_value) for item in formal_trace_before] == [
        ("formal-subject", "present")
    ]
    assert [(item.subject_ref, item.bridge_value) for item in formal_trace_after] == [
        ("formal-subject", "present")
    ]

    assert _family(runtime_before, "operativeStatus")[0].bridge_value == "qualified"
    assert _family(runtime_after, "operativeStatus")[0].bridge_value == "withdrawn"
    assert _family(formal_before, "operativeStatus")[0].bridge_value == "qualified"
    assert _family(formal_after, "operativeStatus")[0].bridge_value == "withdrawn"

    round_trip = O0Snapshot.model_validate_json(runtime_after.model_dump_json())
    assert round_trip == runtime_after


def test_f2_typed_dependency_is_retained_without_forced_semantic_equality() -> None:
    runtime = alpha_r0(
        RuntimeObservationBundle0(
            observed_at=T0,
            relations=[
                RecordRelation(
                    id="relation-1",
                    relation_type="depends-on",
                    subject_ref="runtime-child",
                    object_ref="runtime-parent",
                )
            ],
        )
    )
    formal = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            dependencies=[
                FormalDependencyInput(
                    subject_ref="formal-child",
                    relation_tag="ordered-parent",
                    object_ref="formal-parent",
                )
            ],
        )
    )

    runtime_dep = _family(runtime, "historicalDependency")[0]
    formal_dep = _family(formal, "historicalDependency")[0]

    assert runtime_dep.semantics_tag == "runtime.relation.depends-on"
    assert formal_dep.semantics_tag == "formal.dependency.ordered-parent"
    assert runtime_dep.quality == "ABSTRACTION"
    assert formal_dep.quality == "ABSTRACTION"
    assert runtime_dep.bridge_key is None
    assert formal_dep.bridge_key is None


def test_f3_current_qualification_layers_are_not_flattened() -> None:
    assertion = Assertion(
        id="runtime-subject",
        statement="candidate conclusion",
        epistemic_status="supported",
        lifecycle_status="current",
    )
    grant = AuthorizationGrant(
        id="grant-1",
        principal_ref="owner",
        grantee_ref="agent",
        allowed_capabilities=["read"],
        valid_from=T0 - timedelta(hours=1),
        expires_at=T0 + timedelta(hours=1),
    )
    runtime = alpha_r0(
        RuntimeObservationBundle0(
            observed_at=T0,
            records=[assertion],
            authorization_grants=[grant],
        )
    )
    formal = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            operative_statuses=[
                FormalOperativeStatusInput(
                    subject_ref="formal-warrant",
                    layer="warrant.usable",
                    status="qualified",
                ),
                FormalOperativeStatusInput(
                    subject_ref="formal-license",
                    layer="license.base-current",
                    status="qualified",
                ),
                FormalOperativeStatusInput(
                    subject_ref="formal-context",
                    layer="context.grounded",
                    status="qualified",
                ),
            ],
        )
    )

    runtime_tags = {item.semantics_tag for item in _family(runtime, "operativeStatus")}
    assert runtime_tags == {
        "runtime.assertion-epistemic-status",
        "runtime.authorization-current-at-observedAt",
    }

    formal_layers = {item.coordinates["layer"] for item in _family(formal, "operativeStatus")}
    assert formal_layers == {"warrant.usable", "license.base-current", "context.grounded"}


def test_f4_invalidation_review_does_not_rewrite_historical_trace() -> None:
    impact, assessment = _impact_and_assessment()
    assertion = Assertion(
        id="runtime-subject",
        statement="candidate conclusion",
        epistemic_status="revalidation-required",
        lifecycle_status="current",
    )
    runtime = alpha_r0(
        RuntimeObservationBundle0(
            observed_at=T0,
            records=[assertion],
            impacts=[impact],
            assessments=[assessment],
        )
    )
    formal = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            historical_traces=[
                FormalHistoricalTraceInput(subject_ref="formal-subject", trace_kind="warrant")
            ],
            operative_statuses=[
                FormalOperativeStatusInput(
                    subject_ref="formal-subject",
                    layer="warrant.usable",
                    status="withdrawn",
                )
            ],
            reviews=[
                FormalReviewInput(subject_ref="formal-subject", review_state="review-required")
            ],
        )
    )

    assert _family(runtime, "historicalTrace")[0].bridge_value == "present"
    assert _family(formal, "historicalTrace")[0].bridge_value == "present"
    assert _family(runtime, "reviewInvalidation")
    assert _family(formal, "reviewInvalidation")


def test_f5_impact_observation_is_separate_from_disposition() -> None:
    impact, assessment = _impact_and_assessment()
    runtime = alpha_r0(
        RuntimeObservationBundle0(
            observed_at=T0,
            impacts=[impact],
            assessments=[assessment],
        )
    )
    formal = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            impacts=[
                FormalImpactInput(
                    subject_ref="formal-subject",
                    target_ref="formal-target",
                    propagation="transitive-historical-closure",
                )
            ],
            requirements=[
                FormalRequirementInput(
                    subject_ref="formal-subject",
                    requirement="repair-cut-must-be-hit",
                )
            ],
        )
    )

    assert len(_family(runtime, "impactObservation")) == 1
    assert len(_family(runtime, "dischargeRequirement")) == 1
    assert len(_family(formal, "impactObservation")) == 1
    assert len(_family(formal, "dischargeRequirement")) == 1
    assert _family(runtime, "impactObservation")[0].quality == "SEMANTIC-MISMATCH"
    assert _family(formal, "impactObservation")[0].quality == "SEMANTIC-MISMATCH"


def test_f6_discharge_requirement_is_separate_from_discharge_evidence() -> None:
    _, assessment = _impact_and_assessment()
    revision = RevisionRecord(
        id="revision-1",
        subject_ref="runtime-subject",
        revises_ref="old-1",
        produces_ref="new-1",
        supersedes_ref="old-1",
        lifecycle_status="applied",
    )
    runtime = alpha_r0(
        RuntimeObservationBundle0(
            observed_at=T0,
            records=[revision],
            assessments=[assessment],
        )
    )
    formal = alpha_f0(
        FormalObservationBundle0(
            observed_at=T0,
            requirements=[
                FormalRequirementInput(
                    subject_ref="formal-subject",
                    requirement="selected-repair-required",
                )
            ],
            evidence=[
                FormalEvidenceInput(
                    subject_ref="formal-subject",
                    evidence_kind="repair-realization",
                )
            ],
        )
    )

    assert len(_family(runtime, "dischargeRequirement")) == 1
    assert len(_family(runtime, "dischargeEvidence")) == 1
    assert len(_family(formal, "dischargeRequirement")) == 1
    assert len(_family(formal, "dischargeEvidence")) == 1


def test_ref2_discovers_nonempty_b0_from_adapter_outputs() -> None:
    coordinates = discover_b0(_f1_cases())
    by_key = {coordinate.key: coordinate for coordinate in coordinates}

    assert "historicalTrace:trace.referent-present" in by_key
    assert "operativeStatus:qualification.current" in by_key
    assert by_key["historicalTrace:trace.referent-present"].witnesses == 2
    assert by_key["operativeStatus:qualification.current"].witnesses == 2
    assert all("impact" not in key for key in by_key)
