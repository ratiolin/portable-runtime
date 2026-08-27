from datetime import UTC, datetime

import pytest

from experiments.persistent_agency import (
    Commitment,
    PriorityDimensions,
    PriorityJudgment,
    ResourceEnvelope,
    ResourceRequest,
    SituationAssessment,
    StandingResponsibility,
    WorkProposal,
    WorkRecord,
)
from experiments.responsibility_supervisor import (
    ResourceConsumption,
    ResponsibilitySupervisor,
)


def _mission() -> StandingResponsibility:
    return StandingResponsibility(
        id="mission:listing-integrity",
        statement="Maintain listing integrity.",
        scope={"channel": "shopify"},
    )


def _assessment() -> SituationAssessment:
    return SituationAssessment(
        id="assessment:drift",
        responsibility_ref="mission:listing-integrity",
        subject_ref="listing:SKU-1",
        assessment_kind="drift-detected",
        basis_refs=("shopify-readback:7", "catalog-revision:4"),
        assessed_at=datetime(2026, 8, 27, tzinfo=UTC),
        rationale="current readback differs from qualified catalog state",
    )


def _proposal() -> WorkProposal:
    return WorkProposal(
        id="proposal:diagnose",
        responsibility_ref="mission:listing-integrity",
        assessment_ref="assessment:drift",
        proposed_work_kind="read-only-diagnosis",
        subject_ref="listing:SKU-1",
        resource_request=ResourceRequest(compute_units=3, api_calls=5),
        stop_conditions=("cause-explained",),
        escalation_conditions=("external-write-required",),
    )


def _priority() -> PriorityJudgment:
    return PriorityJudgment(
        id="priority:diagnose",
        proposal_ref="proposal:diagnose",
        dimensions=PriorityDimensions(
            urgency=4,
            impact=3,
            risk=1,
            reversibility=5,
            confidence=4,
            resource_cost=1,
            human_attention_cost=0,
        ),
        admitted=True,
        rationale="bounded diagnosis should proceed now",
    )


def _commitment() -> Commitment:
    return Commitment(
        id="commitment:diagnose",
        responsibility_ref="mission:listing-integrity",
        proposal_ref="proposal:diagnose",
        priority_judgment_ref="priority:diagnose",
        resource_allocation=ResourceRequest(compute_units=3, api_calls=5),
        stop_conditions=("cause-explained",),
        escalation_conditions=("external-write-required",),
        committed_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


def test_supervisor_rejects_proposal_that_skips_situation_assessment():
    supervisor = ResponsibilitySupervisor()
    supervisor.register_responsibility(_mission())

    with pytest.raises(ValueError, match="registered situation assessment"):
        supervisor.register_proposal(_proposal())

    supervisor.register_assessment(_assessment())
    supervisor.register_proposal(_proposal())
    assert "proposal:diagnose" in supervisor.portfolio.proposals


def test_supervisor_rejects_cross_responsibility_assessment_shortcut():
    supervisor = ResponsibilitySupervisor()
    supervisor.register_responsibility(_mission())
    supervisor.register_assessment(_assessment())
    proposal = WorkProposal(
        id="proposal:wrong-mission",
        responsibility_ref="mission:other",
        assessment_ref="assessment:drift",
        proposed_work_kind="read-only-diagnosis",
        subject_ref="listing:SKU-1",
        resource_request=ResourceRequest(compute_units=1),
        stop_conditions=("done",),
        escalation_conditions=(),
    )

    with pytest.raises(ValueError, match="responsibility refs must match"):
        supervisor.register_proposal(proposal)


def test_supervisor_tracks_consumption_against_commitment_not_effect_authority():
    supervisor = ResponsibilitySupervisor()
    supervisor.register_responsibility(_mission())
    supervisor.register_assessment(_assessment())
    supervisor.register_proposal(_proposal())
    supervisor.commit(
        commitment=_commitment(),
        priority=_priority(),
        envelope=ResourceEnvelope(
            compute_units=10,
            api_calls=10,
            money_minor=0,
            human_attention_units=0,
        ),
    )

    first_total = supervisor.record_consumption(
        ResourceConsumption(
            commitment_ref="commitment:diagnose",
            consumed=ResourceRequest(compute_units=1, api_calls=2),
            recorded_at=datetime(2026, 8, 27, 0, 1, tzinfo=UTC),
            evidence_refs=("meter:1",),
        )
    )
    assert first_total == ResourceRequest(compute_units=1, api_calls=2)

    second_total = supervisor.record_consumption(
        ResourceConsumption(
            commitment_ref="commitment:diagnose",
            consumed=ResourceRequest(compute_units=2, api_calls=3),
            recorded_at=datetime(2026, 8, 27, 0, 2, tzinfo=UTC),
            evidence_refs=("meter:2",),
        )
    )
    assert second_total == ResourceRequest(compute_units=3, api_calls=5)

    with pytest.raises(ValueError, match="exceeds committed allocation"):
        supervisor.record_consumption(
            ResourceConsumption(
                commitment_ref="commitment:diagnose",
                consumed=ResourceRequest(api_calls=1),
                recorded_at=datetime(2026, 8, 27, 0, 3, tzinfo=UTC),
            )
        )

    commitment = supervisor.portfolio.commitments["commitment:diagnose"]
    assert commitment.execution_authorization_ref is None
    assert commitment.authority_bearing is False


def test_supervisor_completes_work_without_discharge_of_mission():
    supervisor = ResponsibilitySupervisor()
    mission = _mission()
    supervisor.register_responsibility(mission)
    supervisor.register_assessment(_assessment())
    supervisor.register_proposal(_proposal())
    supervisor.commit(
        commitment=_commitment(),
        priority=_priority(),
        envelope=ResourceEnvelope(
            compute_units=10,
            api_calls=10,
            money_minor=0,
            human_attention_units=0,
        ),
    )
    supervisor.start_work(
        WorkRecord(
            id="work:diagnose",
            commitment_ref="commitment:diagnose",
            responsibility_ref=mission.id,
            work_kind="read-only-diagnosis",
            subject_ref="listing:SKU-1",
        )
    )
    supervisor.complete_work("work:diagnose")

    assert supervisor.portfolio.responsibilities[mission.id].status.value == "active"
