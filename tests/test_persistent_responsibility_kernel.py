from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portable_runtime.responsibility import (
    Commitment,
    EffectClass,
    PortfolioAdmissionDecision,
    PriorityDimensions,
    PriorityJudgment,
    ReasoningSessionBinding,
    ResourcePool,
    ResourceReservation,
    ResourceVector,
    ResponsibilityAdmission,
    ResponsibilityExpectation,
    ResponsibilityHandoff,
    ResponsibilityKernel,
    ResponsibilityLifecycleTransition,
    ResponsibilityRevision,
    ResponsibilityStatus,
    StandingResponsibility,
    WorkProposal,
)
from portable_runtime.stores.bundle import export_bundle, import_bundle
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _now() -> datetime:
    return datetime(2026, 8, 27, 6, 30, tzinfo=UTC)


def _register(kernel: ResponsibilityKernel, responsibility_id: str = "sr_listing") -> StandingResponsibility:
    identity = StandingResponsibility(
        id=responsibility_id,
        responsibility_kind="listing-integrity",
        statement="Maintain listing integrity",
        scope={"shop": "dev", "channel": "online-store"},
    )
    kernel.register(
        identity,
        ResponsibilityAdmission(
            id=f"admission_{responsibility_id}",
            responsibility_ref=identity.id,
            responsibility_version=1,
            principal_ref="principal:owner",
            basis_refs=["decision:mission-admission"],
        ),
    )
    return identity


def _assessment(kernel: ResponsibilityKernel, responsibility_id: str = "sr_listing"):
    now = _now()
    expectation = ResponsibilityExpectation(
        id=f"expectation_{responsibility_id}",
        responsibility_ref=responsibility_id,
        responsibility_version=1,
        subject_ref="shopify:product:1",
        expected_signal_kind="shopify-readback",
        due_at=now - timedelta(minutes=1),
        freshness_window_seconds=600,
    )
    kernel.create_expectation(expectation)
    assessment = kernel.assess_due_expectation(
        expectation.id,
        now=now,
        observed_evidence_refs=[],
    )
    assert assessment is not None
    return assessment


def _proposal_chain(
    kernel: ResponsibilityKernel,
    *,
    effect_class: EffectClass = EffectClass.READ_ONLY,
    responsibility_id: str = "sr_listing",
):
    now = _now()
    assessment = _assessment(kernel, responsibility_id)
    proposal = WorkProposal(
        id=f"proposal_{responsibility_id}",
        responsibility_ref=responsibility_id,
        responsibility_version=1,
        assessment_ref=assessment.id,
        subject_ref="shopify:product:1",
        work_kind="listing-diagnosis",
        title="Diagnose listing drift",
        description="Read current listing state and explain drift.",
        requested_resources=ResourceVector(
            compute_units=1,
            api_calls=2,
            concurrency_slots=1,
        ),
        requested_capabilities=["shopify.read"],
        expected_result="readback evidence and diagnosis artifact",
        effect_class=effect_class,
        fresh_until=now + timedelta(minutes=5),
    )
    kernel.propose(proposal, now=now)

    priority = PriorityJudgment(
        id=f"priority_{responsibility_id}",
        proposal_ref=proposal.id,
        dimensions=PriorityDimensions(
            urgency=3,
            impact=3,
            risk=1,
            reversibility=5,
            confidence=4,
            resource_cost=1,
            human_attention_cost=0,
        ),
        policy_ref="portfolio-policy-v1",
        admitted=True,
        rationale="bounded diagnosis is admissible",
    )
    kernel.record_priority_judgment(priority)

    pool = ResourcePool(
        id="resource_pool_default",
        pool_key="default",
        capacity=ResourceVector(
            compute_units=10,
            api_calls=20,
            money_minor=0,
            human_attention_units=2,
            concurrency_slots=4,
        ),
        policy_ref="portfolio-policy-v1",
    )
    if kernel.journal.get(pool.id) is None:
        kernel.create_resource_pool(pool)

    portfolio = PortfolioAdmissionDecision(
        id=f"portfolio_{responsibility_id}",
        proposal_ref=proposal.id,
        resource_pool_ref=pool.id,
        policy_ref="portfolio-policy-v1",
        admitted=True,
        rationale="capacity is available",
    )
    kernel.record_portfolio_admission(portfolio)

    reservation = ResourceReservation(
        id=f"reservation_{responsibility_id}",
        responsibility_ref=responsibility_id,
        proposal_ref=proposal.id,
        resource_pool_ref=pool.id,
        resources=proposal.requested_resources,
        reserved_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    kernel.reserve(reservation, now=now)

    commitment = Commitment(
        id=f"commitment_{responsibility_id}",
        responsibility_ref=responsibility_id,
        responsibility_version=1,
        proposal_ref=proposal.id,
        priority_judgment_ref=priority.id,
        portfolio_admission_ref=portfolio.id,
        reservation_ref=reservation.id,
        resources=proposal.requested_resources,
        committed_at=now,
        stop_conditions=["stop if scope version changes"],
        escalation_conditions=["escalate before external mutation"],
    )
    kernel.commit(commitment, now=now)
    return proposal, commitment


def test_standing_responsibility_survives_state_export_import() -> None:
    source = InMemoryStateStore()
    source_kernel = ResponsibilityKernel(source)
    _register(source_kernel)
    _assessment(source_kernel)

    state = source.export_state()
    target = InMemoryStateStore()
    target.import_state(state)
    target_kernel = ResponsibilityKernel(target)

    assert target_kernel.current_status("sr_listing") is ResponsibilityStatus.ACTIVE
    assert target_kernel.get_responsibility("sr_listing").statement == "Maintain listing integrity"
    assert len(target_kernel.journal.list("ResponsibilityExpectation", "sr_listing")) == 1


def test_standing_responsibility_survives_sqlite_restart(tmp_path) -> None:
    path = tmp_path / "runtime.db"
    first = SQLiteStateStore(path)
    first_kernel = ResponsibilityKernel(first)
    _register(first_kernel)
    _assessment(first_kernel)
    first.close()

    reopened = SQLiteStateStore(path)
    reopened_kernel = ResponsibilityKernel(reopened)
    assert reopened_kernel.current_status("sr_listing") is ResponsibilityStatus.ACTIVE
    assert len(reopened_kernel.journal.list("ResponsibilityAssessment", "sr_listing")) == 1
    reopened.close()


def test_bundle_round_trip_preserves_responsibility_without_minting_authority(tmp_path) -> None:
    source = InMemoryStateStore()
    kernel = ResponsibilityKernel(source)
    _register(kernel)
    _proposal_chain(kernel, effect_class=EffectClass.EXTERNAL_EFFECT)
    bundle = tmp_path / "state.tar"
    export_bundle(source, None, bundle, runtime_id="source")

    target = InMemoryStateStore()
    import_bundle(target, None, bundle)
    target_kernel = ResponsibilityKernel(target)

    assert target_kernel.current_status("sr_listing") is ResponsibilityStatus.ACTIVE
    assert target.list_authorizations() == []
    assert len(target_kernel.journal.list("Commitment", "sr_listing")) == 1


def test_duplicate_wakeup_replays_one_logical_assessment() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    now = _now()
    expectation = ResponsibilityExpectation(
        id="expectation_readback",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        subject_ref="shopify:product:1",
        expected_signal_kind="shopify-readback",
        due_at=now - timedelta(seconds=1),
    )
    kernel.create_expectation(expectation)

    first = kernel.assess_due_expectation(expectation.id, now=now, observed_evidence_refs=[])
    second = kernel.assess_due_expectation(expectation.id, now=now, observed_evidence_refs=[])

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert len(kernel.journal.list("ResponsibilityAssessment", "sr_listing")) == 1


def test_external_effect_commitment_materializes_work_but_not_authority() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    _proposal, commitment = _proposal_chain(kernel, effect_class=EffectClass.EXTERNAL_EFFECT)

    work = kernel.materialize_work(commitment.id)

    assert work.metadata["external_effect_authority"] == "required-separately"
    assert work.metadata["standing_responsibility_ref"] == "sr_listing"
    assert store.list_authorizations() == []
    assert kernel.current_status("sr_listing") is ResponsibilityStatus.ACTIVE


def test_scope_revision_makes_historical_proposal_ineligible() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    assessment = _assessment(kernel)
    old_proposal = WorkProposal(
        id="proposal_old",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        assessment_ref=assessment.id,
        subject_ref="shopify:product:1",
        work_kind="listing-diagnosis",
        title="Old proposal",
        effect_class=EffectClass.READ_ONLY,
    )

    kernel.revise(
        ResponsibilityRevision(
            id="revision_2",
            responsibility_ref="sr_listing",
            from_version=1,
            to_version=2,
            statement="Maintain listing integrity",
            scope={"shop": "dev", "channel": "online-store", "market": "jp"},
            basis_refs=["decision:scope-change"],
        )
    )

    with pytest.raises(ValueError, match="historical proposal"):
        kernel.propose(old_proposal, now=_now())


def test_resource_pool_prevents_overcommit() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    assessment = _assessment(kernel)
    pool = ResourcePool(
        id="small_pool",
        pool_key="small",
        capacity=ResourceVector(compute_units=1, api_calls=1, concurrency_slots=1),
        policy_ref="portfolio-policy-v1",
    )
    kernel.create_resource_pool(pool)

    for suffix in ("a", "b"):
        proposal = WorkProposal(
            id=f"proposal_{suffix}",
            responsibility_ref="sr_listing",
            responsibility_version=1,
            assessment_ref=assessment.id,
            subject_ref=f"subject:{suffix}",
            work_kind="diagnosis",
            title=f"diagnosis {suffix}",
            requested_resources=ResourceVector(compute_units=1, api_calls=1, concurrency_slots=1),
        )
        kernel.propose(proposal, now=_now())

    first = ResourceReservation(
        id="reservation_a",
        responsibility_ref="sr_listing",
        proposal_ref="proposal_a",
        resource_pool_ref=pool.id,
        resources=ResourceVector(compute_units=1, api_calls=1, concurrency_slots=1),
    )
    kernel.reserve(first, now=_now())

    second = ResourceReservation(
        id="reservation_b",
        responsibility_ref="sr_listing",
        proposal_ref="proposal_b",
        resource_pool_ref=pool.id,
        resources=ResourceVector(compute_units=1, api_calls=1, concurrency_slots=1),
    )
    with pytest.raises(ValueError, match="overcommit"):
        kernel.reserve(second, now=_now())


def test_model_handoff_preserves_identity_but_requires_authority_revalidation() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    from_binding = ReasoningSessionBinding(
        id="session_a",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        provider="provider-a",
        model="model-a",
        session_ref="session:a",
    )
    to_binding = ReasoningSessionBinding(
        id="session_b",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        provider="provider-b",
        model="model-b",
        session_ref="session:b",
    )
    kernel.bind_reasoning_session(from_binding)
    kernel.bind_reasoning_session(to_binding)
    snapshot = kernel.create_context_snapshot("sr_listing")
    handoff = ResponsibilityHandoff(
        id="handoff_a_b",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        from_session_ref=from_binding.id,
        to_session_ref=to_binding.id,
        context_snapshot_ref=snapshot.id,
    )
    kernel.handoff(handoff)
    validation = kernel.validate_handoff(handoff.id, now=_now())

    assert validation.continuity_ok is True
    assert validation.authorization_revalidation_required is True
    assert kernel.get_responsibility("sr_listing").id == "sr_listing"


def test_discharge_requires_explicit_decision_and_work_does_not_discharge() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(kernel)
    _proposal, commitment = _proposal_chain(kernel)
    kernel.materialize_work(commitment.id)

    assert kernel.current_status("sr_listing") is ResponsibilityStatus.ACTIVE

    with pytest.raises(ValueError, match="decision_ref"):
        ResponsibilityLifecycleTransition(
            id="bad_discharge",
            responsibility_ref="sr_listing",
            responsibility_version=1,
            from_status=ResponsibilityStatus.ACTIVE,
            to_status=ResponsibilityStatus.DISCHARGED,
            reason="work finished",
        )

    transition = ResponsibilityLifecycleTransition(
        id="discharge",
        responsibility_ref="sr_listing",
        responsibility_version=1,
        from_status=ResponsibilityStatus.ACTIVE,
        to_status=ResponsibilityStatus.DISCHARGED,
        decision_ref="decision:explicit-discharge",
        basis_refs=["verification:scope-complete"],
    )
    kernel.transition(transition)
    assert kernel.current_status("sr_listing") is ResponsibilityStatus.DISCHARGED
