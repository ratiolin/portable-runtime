from __future__ import annotations

from portable_runtime.core.reliability import ReliabilityControls


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
