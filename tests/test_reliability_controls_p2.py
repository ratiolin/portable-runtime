from __future__ import annotations

from portable_runtime.core.reliability import (
    CircuitBreaker,
    DefaultLocalReliabilityPolicy,
    ReliabilityControls,
    ReliabilityDisposition,
    ReliabilityLimits,
    ReliabilityObservation,
    ReliabilityRiskEvaluator,
    ReliabilityRiskAssessment,
)


def test_circuit_breaker_reopens_after_recovery_and_closes_on_probe_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
    assert breaker.allow()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state == "closed"


def test_reliability_blocks_parallel_side_effects_and_releases_capacity() -> None:
    controls = ReliabilityControls(
        max_parallel_side_effects=1,
        cooldown_seconds=0,
        blast_radius=3,
        exposure_budget=10,
    )

    assert controls.can_execute(side_effect=True, action_blast_radius=2)
    controls.record_action(side_effect=True, action_blast_radius=2)
    assert controls.active_side_effects == 1
    assert not controls.can_execute(side_effect=True, action_blast_radius=1)
    assert controls.last_block_reason == "max_parallel_side_effects exceeded"

    controls.complete_action(side_effect=True)
    assert controls.active_side_effects == 0
    assert controls.can_execute(side_effect=True, action_blast_radius=1)


def test_reliability_enforces_blast_radius_and_exposure_budget() -> None:
    controls = ReliabilityControls(
        cooldown_seconds=0,
        blast_radius=2,
        exposure_budget=3,
    )

    assert not controls.can_execute(side_effect=True, action_blast_radius=3)
    assert controls.last_block_reason == "blast_radius 3 exceeds limit 2"
    assert controls.can_execute(side_effect=True, action_blast_radius=2, exposure=2)
    controls.record_action(side_effect=True, action_blast_radius=2, exposure=2)
    controls.complete_action(side_effect=True)
    assert not controls.can_execute(side_effect=True, action_blast_radius=1, exposure=2)
    assert controls.last_block_reason == "exposure_budget exhausted"


def test_reliability_separates_policy_profile_risk_and_disposition() -> None:
    policy = DefaultLocalReliabilityPolicy(profile_id="test-policy", version="9", blast_radius=2)
    controls = ReliabilityControls(policy=policy)
    assert controls.can_execute(side_effect=True, action_blast_radius=1, exposure=1)
    controls.record_action(side_effect=True, action_blast_radius=1, exposure=1)
    assert not controls.can_execute(side_effect=True, action_blast_radius=3)
    assert isinstance(controls.last_risk_assessment, ReliabilityRiskAssessment)
    assert isinstance(controls.last_disposition, ReliabilityDisposition)
    assert controls.last_disposition.policy_ref == "test-policy@9"
    assert "blast_radius_limit" in controls.last_risk_assessment.reason_refs


def test_enhanced_profile_requires_fast_recovery_loop() -> None:
    controls = ReliabilityControls(cooldown_seconds=0)
    assert not controls.can_execute(side_effect=True, procedure_profile="enhanced")
    assert controls.last_block_reason == "enhanced side effect requires recovery timing"

    timing = {
        "t_detect": 1,
        "t_judge": 1,
        "t_correct": 1,
        "t_irreversible": 4,
    }
    assert controls.can_execute(
        side_effect=True,
        procedure_profile="enhanced",
        timing=timing,
    )
    timing["t_correct"] = 3
    assert not controls.can_execute(
        side_effect=True,
        procedure_profile="enhanced",
        timing=timing,
    )
    assert controls.last_block_reason == "recovery loop exceeds irreversible window"


def test_risk_evaluator_and_policy_decision_are_independent() -> None:
    observation = ReliabilityObservation(
        action_rate=0,
        active_side_effects=0,
        side_effect_count=0,
        exposure_used=0,
        requested_blast_radius=4,
        requested_exposure=1,
        cooldown_remaining=0,
    )
    evaluator = ReliabilityRiskEvaluator()
    risk = evaluator.evaluate(
        observation,
        ReliabilityLimits(blast_radius=2),
        side_effect=True,
        irreversible=False,
        procedure_profile=None,
        timing=None,
    )
    policy = DefaultLocalReliabilityPolicy(profile_id="split", version="1", blast_radius=2)
    disposition = policy.decide(observation, risk)
    assert risk.reason_refs == ("blast_radius_limit",)
    assert disposition.action == "deny"
    assert disposition.reason == "blast_radius 4 exceeds limit 2"
