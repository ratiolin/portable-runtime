from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from portable_runtime.observation.raw_transition import build_raw_withdrawal_transition
from portable_runtime.records.models import Assertion

FIXTURE = Path(__file__).parent / "fixtures" / "o0" / "raw_withdrawal_transition_v1.json"


def _before_assertion() -> Assertion:
    return Assertion(
        id="assertion-ref4-1",
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
        created_by="ref4-fixture",
        source_refs=["evidence-ref4-1"],
        environment_versions={"validator": "v1"},
        invalidation_conditions=["validator-change"],
        lifecycle_status="current",
        epistemic_status="supported",
        version=7,
        metadata={"fixture": "ref4"},
        statement="selected assertion remains historically recorded",
    )


def _executable_transition():
    before = _before_assertion()
    after = before.model_copy(
        update={
            "epistemic_status": "revalidation-required",
            "version": 8,
        }
    )
    return build_raw_withdrawal_transition(
        before,
        after,
        event_ref="fixture-transition:assertion-ref4-1:7-8",
    )


def test_committed_raw_artifact_matches_executable_transition() -> None:
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    generated = _executable_transition().model_dump(mode="json")
    assert committed == generated


def test_raw_artifact_contains_no_b0_derived_fields() -> None:
    raw_text = FIXTURE.read_text(encoding="utf-8")
    for forbidden in (
        "historical_trace_before",
        "historical_trace_after",
        "qualification_before",
        "qualification_after",
        "b0_coordinates",
        "bridge_key",
        "bridge_value",
    ):
        assert forbidden not in raw_text


def test_builder_does_not_prejudge_b0_withdrawal() -> None:
    before = _before_assertion()
    after = before.model_copy(update={"epistemic_status": "contested", "version": 8})
    artifact = build_raw_withdrawal_transition(before, after, event_ref="fixture:non-withdrawal")
    assert artifact.after_raw_snapshot["epistemic_status"] == "contested"


def test_builder_rejects_cross_subject_envelope() -> None:
    before = _before_assertion()
    after = before.model_copy(update={"id": "other-assertion"})
    with pytest.raises(ValueError, match="same assertion id"):
        build_raw_withdrawal_transition(before, after, event_ref="fixture:mismatch")
