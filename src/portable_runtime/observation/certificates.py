"""Certificate extraction for the first restricted observational fragment.

Extraction is intentionally outside the verified checker trust boundary.  The
certificate records only B0 observations already emitted by REF-2 adapters.  A
Lean checker in ``responsibility_topology`` verifies the abstract certificate
contract; this module does not claim to verify the runtime implementation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.observation.o0 import O0Observation, O0Snapshot

QualificationState = Literal["qualified", "withdrawn"]


class QualificationWithdrawalCertificate(BaseModel):
    """Versioned certificate for history-retaining qualification withdrawal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["o0-withdrawal-cert-v1"] = "o0-withdrawal-cert-v1"
    fragment: Literal["history-retaining-qualification-withdrawal"] = (
        "history-retaining-qualification-withdrawal"
    )
    subject_ref: str
    historical_trace_before: bool
    historical_trace_after: bool
    qualification_before: QualificationState
    qualification_after: QualificationState
    accepted_discharge_evidence_after: bool = False
    b0_coordinates: list[str] = Field(default_factory=list)
    source_semantics_tags: list[str] = Field(default_factory=list)


def _find_bridge_observation(
    snapshot: O0Snapshot,
    *,
    family: str,
    subject_ref: str,
    bridge_key: str,
) -> O0Observation | None:
    for observation in snapshot.observations:
        if observation.family != family:
            continue
        if observation.subject_ref != subject_ref:
            continue
        if observation.bridge_key != bridge_key:
            continue
        if observation.quality in {"SEMANTIC-MISMATCH", "NOT-REPRESENTED"}:
            continue
        return observation
    return None


def _accepted_discharge_evidence(snapshot: O0Snapshot, subject_ref: str) -> bool:
    return any(
        observation.family == "dischargeEvidence"
        and observation.subject_ref == subject_ref
        and observation.bridge_key == "discharge.accepted"
        and observation.bridge_value == "accepted"
        and observation.quality not in {"SEMANTIC-MISMATCH", "NOT-REPRESENTED"}
        for observation in snapshot.observations
    )


def build_qualification_withdrawal_certificate(
    before: O0Snapshot,
    after: O0Snapshot,
    *,
    subject_ref: str,
) -> QualificationWithdrawalCertificate:
    """Extract the first B0 certificate from two runtime O0 snapshots.

    The function requires the REF-2 B0 observations to be present.  It refuses
    to manufacture a certificate from source-specific impact/disposition data.
    """

    if before.origin != "runtime" or after.origin != "runtime":
        raise ValueError("qualification withdrawal certificates require runtime O0 snapshots")
    if after.observed_at < before.observed_at:
        raise ValueError("after snapshot must not precede before snapshot")

    trace_before = _find_bridge_observation(
        before,
        family="historicalTrace",
        subject_ref=subject_ref,
        bridge_key="trace.referent-present",
    )
    trace_after = _find_bridge_observation(
        after,
        family="historicalTrace",
        subject_ref=subject_ref,
        bridge_key="trace.referent-present",
    )
    status_before = _find_bridge_observation(
        before,
        family="operativeStatus",
        subject_ref=subject_ref,
        bridge_key="qualification.current",
    )
    status_after = _find_bridge_observation(
        after,
        family="operativeStatus",
        subject_ref=subject_ref,
        bridge_key="qualification.current",
    )

    if trace_before is None or trace_after is None:
        raise ValueError("B0 historical-trace coordinate is missing")
    if status_before is None or status_after is None:
        raise ValueError("B0 qualification coordinate is missing")
    if status_before.bridge_value != "qualified":
        raise ValueError("before snapshot is not B0-qualified")
    if status_after.bridge_value != "withdrawn":
        raise ValueError("after snapshot is not B0-withdrawn")

    return QualificationWithdrawalCertificate(
        subject_ref=subject_ref,
        historical_trace_before=trace_before.bridge_value == "present",
        historical_trace_after=trace_after.bridge_value == "present",
        qualification_before="qualified",
        qualification_after="withdrawn",
        accepted_discharge_evidence_after=_accepted_discharge_evidence(after, subject_ref),
        b0_coordinates=[
            "historicalTrace:trace.referent-present",
            "operativeStatus:qualification.current",
        ],
        source_semantics_tags=[
            trace_before.semantics_tag,
            trace_after.semantics_tag,
            status_before.semantics_tag,
            status_after.semantics_tag,
        ],
    )


def render_lean_certificate(
    certificate: QualificationWithdrawalCertificate,
    *,
    definition_name: str = "runtimeCertificate",
) -> str:
    """Render certificate values as a Lean checker input fixture.

    The renderer is not part of the verified checker TCB.  Lean re-checks the
    resulting values against the abstract contract.
    """

    trace_before = "true" if certificate.historical_trace_before else "false"
    trace_after = "true" if certificate.historical_trace_after else "false"
    discharge = "true" if certificate.accepted_discharge_evidence_after else "false"
    before_state = f".{certificate.qualification_before}"
    after_state = f".{certificate.qualification_after}"

    lines = [
        "import ResponsibilityTopology.Bridge.CertifiedObservation",
        "",
        "open ResponsibilityTopology.Bridge",
        "",
        f"def {definition_name} : QualificationWithdrawalCertificate where",
        f"  historicalTraceBefore := {trace_before}",
        f"  historicalTraceAfter := {trace_after}",
        f"  qualificationBefore := {before_state}",
        f"  qualificationAfter := {after_state}",
        f"  acceptedDischargeEvidenceAfter := {discharge}",
        "",
        f"example : checkQualificationWithdrawal {definition_name} = true := by decide",
    ]
    if not certificate.accepted_discharge_evidence_after:
        lines.extend(
            [
                "",
                (
                    "example : currentUseContinuationAccepted "
                    f"{definition_name} = false := by decide"
                ),
            ]
        )
    lines.append("")
    return "\n".join(lines)
