from datetime import datetime, timedelta, timezone

import pytest

from experiments.persistent_agency import (
    CANDIDATE_NON_EQUIVALENCES,
    Commitment,
    EscalationPolicy,
    EscalationRoute,
    ExpectedSignal,
    PriorityDimensions,
    PriorityJudgment,
    ProposalStatus,
    ResourceEnvelope,
    ResourceRequest,
    ResponsibilityPortfolio,
    ResponsibilityStatus,
    RoleDelegation,
    StandingResponsibility,
    WorkProposal,
    WorkRecord,
    WorkStatus,
    assess_missing_signal,
)


def _mission() -> StandingResponsibility:
    return StandingResponsibility(
        id="mission:listing-integrity",
        statement="Maintain listing integrity against currently qualified catalog state.",
        scope={"channel": "shopify"},
    )


def _proposal() -> WorkProposal:
    return WorkProposal(
        id="proposal:sku-1",
        responsibility_ref="mission:listing-integrity",
        assessment_ref="assessment:sku-1",
        proposed_work_kind="listing-integrity-diagnosis",
        subject_ref="listing:SKU-1",
        resource_request=ResourceRequest(compute_units=2, api_calls=4),
        stop_conditions=("drift-explained",),
        escalation_conditions=("external-write-required",),
    )


def _priority() -> PriorityJudgment:
    return PriorityJudgment(
        id="priority:sku-1",
        proposal_ref="proposal:sku-1",
        dimensions=PriorityDimensions(
            urgency=3,
            impact=3,
            risk=2,
            reversibility=5,
            confidence=4,
            resource_cost=1,
            human_attention_cost=0,
        ),
        admitted=True,
        rationale="bounded read-only diagnosis is worth the resources",
    )


def _commitment() -> Commitment:
    return Commitment(
        id="commitment:sku-1",
        responsibility_ref="mission:listing-integrity",
        proposal_ref="proposal:sku-1",
        priority_judgment_ref="priority:sku-1",
        resource_allocation=ResourceRequest(compute_units=2, api_calls=4),
        stop_conditions=("drift-explained",),
        escalation_conditions=("external-write-required",),
        committed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )


def test_candidate_non_equivalences_are_explicit_and_experimental():
    assert len(CANDIDATE_NON_EQUIVALENCES) == 10
    assert ("WorkProposal", "Commitment") in CANDIDATE_NON_EQUIVALENCES
    assert ("TaskCompleted", "StandingResponsibilityDischarged") in CANDIDATE_NON_EQUIVALENCES
    assert ("NoObservedFailure", "ConditionVerifiedHealthy") in CANDIDATE_NON_EQUIVALENCES


def test_work_proposal_does_not_commit_resources_or_mint_authority():
    proposal = _proposal()
    assert proposal.status is ProposalStatus.PROPOSED
    assert proposal.authority_bearing is False


def test_commitment_requires_admitted_priority_and_resource_envelope():
    portfolio = ResponsibilityPortfolio()
    portfolio.add_responsibility(_mission())
    proposal = _proposal()
    portfolio.add_proposal(proposal)

    rejected = PriorityJudgment(
        id="priority:sku-1",
        proposal_ref=proposal.id,
        dimensions=_priority().dimensions,
        admitted=False,
        rationale="defer",
    )
    with pytest.raises(ValueError, match="rejected proposal"):
        portfolio.commit(
            commitment=_commitment(),
            priority=rejected,
            envelope=ResourceEnvelope(
                compute_units=10,
                api_calls=10,
                money_minor=0,
                human_attention_units=0,
            ),
        )

    with pytest.raises(ValueError, match="exceeds"):
        portfolio.commit(
            commitment=_commitment(),
            priority=_priority(),
            envelope=ResourceEnvelope(
                compute_units=1,
                api_calls=10,
                money_minor=0,
                human_attention_units=0,
            ),
        )


def test_task_completion_does_not_discharge_standing_responsibility():
    portfolio = ResponsibilityPortfolio()
    mission = _mission()
    portfolio.add_responsibility(mission)
    portfolio.add_proposal(_proposal())
    portfolio.commit(
        commitment=_commitment(),
        priority=_priority(),
        envelope=ResourceEnvelope(
            compute_units=10,
            api_calls=10,
            money_minor=0,
            human_attention_units=0,
        ),
    )
    running = portfolio.start_work(
        WorkRecord(
            id="work:sku-1",
            commitment_ref="commitment:sku-1",
            responsibility_ref=mission.id,
            work_kind="listing-integrity-diagnosis",
            subject_ref="listing:SKU-1",
        )
    )
    assert running.status is WorkStatus.RUNNING

    completed = portfolio.complete_work(running.id)
    assert completed.status is WorkStatus.COMPLETED
    assert portfolio.responsibilities[mission.id].status is ResponsibilityStatus.ACTIVE

    portfolio.discharge_responsibility(mission.id)
    assert portfolio.responsibilities[mission.id].status is ResponsibilityStatus.DISCHARGED


def test_missing_expected_signal_can_create_situation_but_not_work():
    mission = _mission()
    due = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)
    expectation = ExpectedSignal(
        id="expectation:daily-reconciliation",
        subject_ref="listing:SKU-1",
        due_at=due,
        evidence_kind="shopify-readback",
    )
    assert (
        assess_missing_signal(
            responsibility=mission,
            expectation=expectation,
            now=due - timedelta(seconds=1),
            observed_evidence_refs=(),
            assessment_id="assessment:not-yet",
        )
        is None
    )
    assert (
        assess_missing_signal(
            responsibility=mission,
            expectation=expectation,
            now=due + timedelta(minutes=5),
            observed_evidence_refs=("readback:present",),
            assessment_id="assessment:present",
        )
        is None
    )

    assessment = assess_missing_signal(
        responsibility=mission,
        expectation=expectation,
        now=due + timedelta(minutes=5),
        observed_evidence_refs=(),
        assessment_id="assessment:missing",
    )
    assert assessment is not None
    assert assessment.assessment_kind == "expected-signal-missing"
    assert assessment.authority_bearing is False


def test_escalation_policy_keeps_autonomy_separate_from_authority():
    policy = EscalationPolicy()
    assert (
        policy.route(external_effect=False, financial_effect=False, reversible=True)
        is EscalationRoute.AUTONOMOUS
    )
    assert (
        policy.route(external_effect=True, financial_effect=True, reversible=True)
        is EscalationRoute.HUMAN_REVIEW
    )
    assert (
        policy.route(external_effect=True, financial_effect=False, reversible=False)
        is EscalationRoute.HUMAN_REVIEW
    )
    assert (
        policy.route(
            external_effect=True,
            financial_effect=False,
            reversible=True,
            explicitly_prohibited=True,
        )
        is EscalationRoute.PROHIBITED
    )


def test_role_delegation_does_not_imply_subdelegation():
    delegation = RoleDelegation(
        id="delegation:catalog-steward",
        principal_ref="human:catalog-owner",
        delegate_ref="agent:listing-steward",
        responsibility_ref="mission:listing-integrity",
    )
    assert delegation.may_subdelegate is False
