from datetime import UTC, datetime
from pathlib import Path

import pytest

from portable_runtime.observation import (
    QualificationWithdrawalCertificate,
    RuntimeObservationBundle0,
    alpha_r0,
    build_qualification_withdrawal_certificate,
    render_lean_certificate,
)
from portable_runtime.records.models import Assertion

T0 = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
FIXTURE = Path("tests/fixtures/o0/qualification_withdrawal_certificate.json")


def _runtime_snapshots():
    before = Assertion(
        id="runtime-subject",
        statement="candidate conclusion",
        epistemic_status="supported",
        lifecycle_status="current",
    )
    after = before.model_copy(update={"epistemic_status": "revalidation-required"})
    return (
        alpha_r0(RuntimeObservationBundle0(observed_at=T0, records=[before])),
        alpha_r0(RuntimeObservationBundle0(observed_at=T0, records=[after])),
    )


def test_builder_matches_frozen_runtime_fixture() -> None:
    before, after = _runtime_snapshots()
    certificate = build_qualification_withdrawal_certificate(
        before,
        after,
        subject_ref="runtime-subject",
    )
    expected = QualificationWithdrawalCertificate.model_validate_json(FIXTURE.read_text())

    assert certificate == expected
    assert certificate.b0_coordinates == [
        "historicalTrace:trace.referent-present",
        "operativeStatus:qualification.current",
    ]
    assert certificate.accepted_discharge_evidence_after is False


def test_renderer_emits_lean_checker_input_not_a_verification_claim() -> None:
    before, after = _runtime_snapshots()
    certificate = build_qualification_withdrawal_certificate(
        before,
        after,
        subject_ref="runtime-subject",
    )
    rendered = render_lean_certificate(certificate)

    assert "import ResponsibilityTopology.Bridge.CertifiedObservation" in rendered
    assert "checkQualificationWithdrawal runtimeCertificate = true" in rendered
    assert "currentUseContinuationAccepted runtimeCertificate = false" in rendered
    assert "historicalTraceBefore := true" in rendered
    assert "qualificationAfter := .withdrawn" in rendered


def test_builder_refuses_non_withdrawal_snapshot() -> None:
    before, _ = _runtime_snapshots()

    with pytest.raises(ValueError, match="after snapshot is not B0-withdrawn"):
        build_qualification_withdrawal_certificate(
            before,
            before,
            subject_ref="runtime-subject",
        )
