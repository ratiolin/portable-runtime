from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from portable_runtime.responsibility.domain import record_domain_assessment
from portable_runtime.responsibility.models import (
    EffectClass,
    ResourceVector,
    ResponsibilityAssessment,
    WorkProposal,
)
from portable_runtime.responsibility.service import ResponsibilityKernel


class ListingIntegrityState(StrEnum):
    HEALTH_VERIFIED = "health-verified"
    DRIFT_DETECTED = "drift-detected"
    QUALIFICATION_NOT_CURRENT = "qualification-not-current"
    EXPECTED_READBACK_MISSING = "expected-readback-missing"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class DeploymentHealthState(StrEnum):
    HEALTH_VERIFIED = "health-verified"
    ALERT_ACTIVE = "alert-active"
    RECOVERY_NOT_VERIFIED = "recovery-not-verified"
    CANDIDATE_CHANGE_NEEDED = "candidate-change-needed"
    DEPLOYMENT_PROPOSED = "deployment-proposed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


def assess_listing_integrity(
    kernel: ResponsibilityKernel,
    *,
    responsibility_ref: str,
    subject_ref: str,
    state: ListingIntegrityState,
    evidence_refs: list[str],
    now: datetime,
) -> ResponsibilityAssessment:
    version, _statement, _scope = kernel.current_definition(responsibility_ref)
    assessment = ResponsibilityAssessment(
        id=f"assessment_listing_{responsibility_ref}_{subject_ref}_{state.value}",
        responsibility_ref=responsibility_ref,
        responsibility_version=version,
        subject_ref=subject_ref,
        assessment_kind=f"listing-integrity:{state.value}",
        basis_refs=evidence_refs,
        assessed_at=now,
        fresh_until=now + timedelta(minutes=15),
        rationale=(
            "Commerce facts remain domain-owned; this object records only the "
            "portable responsibility assessment."
        ),
    )
    return record_domain_assessment(kernel, assessment, now=now)


def listing_integrity_proposal(
    assessment: ResponsibilityAssessment,
    *,
    state: ListingIntegrityState,
    now: datetime,
) -> WorkProposal | None:
    if state in {
        ListingIntegrityState.HEALTH_VERIFIED,
        ListingIntegrityState.INSUFFICIENT_EVIDENCE,
    }:
        return None
    if state in {
        ListingIntegrityState.DRIFT_DETECTED,
        ListingIntegrityState.EXPECTED_READBACK_MISSING,
    }:
        return WorkProposal(
            id=f"proposal_listing_diagnosis_{assessment.id}",
            responsibility_ref=assessment.responsibility_ref,
            responsibility_version=assessment.responsibility_version,
            assessment_ref=assessment.id,
            subject_ref=assessment.subject_ref,
            work_kind="listing-integrity-diagnosis",
            title="Diagnose current listing integrity",
            description="Read current Commerce/Shopify state and produce diagnosis evidence only.",
            requested_resources=ResourceVector(compute_units=1, api_calls=3, concurrency_slots=1),
            requested_capabilities=["commerce.read", "shopify.read"],
            expected_result="current readback and diagnosis artifact",
            stop_conditions=["stop if responsibility scope/version changes"],
            escalation_conditions=["external repair requires separate Commerce Decision and Authorization"],
            effect_class=EffectClass.READ_ONLY,
            fresh_until=now + timedelta(minutes=10),
        )
    if state is ListingIntegrityState.QUALIFICATION_NOT_CURRENT:
        return WorkProposal(
            id=f"proposal_listing_requalification_{assessment.id}",
            responsibility_ref=assessment.responsibility_ref,
            responsibility_version=assessment.responsibility_version,
            assessment_ref=assessment.id,
            subject_ref=assessment.subject_ref,
            work_kind="listing-requalification-preparation",
            title="Prepare listing requalification evidence",
            description=(
                "Prepare bounded evidence for Commerce-owned publication qualification; "
                "do not restore qualification."
            ),
            requested_resources=ResourceVector(compute_units=1, api_calls=2, concurrency_slots=1),
            requested_capabilities=["commerce.read", "shopify.read"],
            expected_result="requalification evidence package",
            stop_conditions=["stop if revision fingerprint or channel context changes"],
            escalation_conditions=["qualification change remains Commerce-owned"],
            effect_class=EffectClass.READ_ONLY,
            fresh_until=now + timedelta(minutes=10),
        )
    return None


def assess_deployment_health(
    kernel: ResponsibilityKernel,
    *,
    responsibility_ref: str,
    subject_ref: str,
    state: DeploymentHealthState,
    evidence_refs: list[str],
    now: datetime,
) -> ResponsibilityAssessment:
    version, _statement, _scope = kernel.current_definition(responsibility_ref)
    assessment = ResponsibilityAssessment(
        id=f"assessment_deploy_{responsibility_ref}_{subject_ref}_{state.value}",
        responsibility_ref=responsibility_ref,
        responsibility_version=version,
        subject_ref=subject_ref,
        assessment_kind=f"deployment-health:{state.value}",
        basis_refs=evidence_refs,
        assessed_at=now,
        fresh_until=now + timedelta(minutes=10),
        rationale=(
            "Monitoring and repository/runtime facts remain profile-owned; "
            "this records only the portable assessment."
        ),
    )
    return record_domain_assessment(kernel, assessment, now=now)


def deployment_health_proposal(
    assessment: ResponsibilityAssessment,
    *,
    state: DeploymentHealthState,
    now: datetime,
) -> WorkProposal | None:
    if state in {
        DeploymentHealthState.HEALTH_VERIFIED,
        DeploymentHealthState.INSUFFICIENT_EVIDENCE,
    }:
        return None
    if state in {
        DeploymentHealthState.ALERT_ACTIVE,
        DeploymentHealthState.RECOVERY_NOT_VERIFIED,
    }:
        return WorkProposal(
            id=f"proposal_deploy_diagnosis_{assessment.id}",
            responsibility_ref=assessment.responsibility_ref,
            responsibility_version=assessment.responsibility_version,
            assessment_ref=assessment.id,
            subject_ref=assessment.subject_ref,
            work_kind="deployment-health-diagnosis",
            title="Diagnose deployment health",
            description=(
                "Read metrics, logs and repository/runtime state; produce diagnosis "
                "without host mutation."
            ),
            requested_resources=ResourceVector(compute_units=2, api_calls=5, concurrency_slots=1),
            requested_capabilities=["metrics.read", "logs.read", "code.read"],
            expected_result="diagnosis with current evidence and bounded repair options",
            stop_conditions=["stop when facts are stale or target version changes"],
            escalation_conditions=["host or deployment mutation requires separate authorization"],
            effect_class=EffectClass.READ_ONLY,
            fresh_until=now + timedelta(minutes=8),
        )
    if state is DeploymentHealthState.CANDIDATE_CHANGE_NEEDED:
        return WorkProposal(
            id=f"proposal_candidate_patch_{assessment.id}",
            responsibility_ref=assessment.responsibility_ref,
            responsibility_version=assessment.responsibility_version,
            assessment_ref=assessment.id,
            subject_ref=assessment.subject_ref,
            work_kind="candidate-patch",
            title="Prepare isolated candidate repair",
            description=(
                "Prepare and test an isolated candidate patch; do not merge, deploy "
                "or mutate host runtime."
            ),
            requested_resources=ResourceVector(compute_units=4, api_calls=4, concurrency_slots=1),
            requested_capabilities=["code.read", "code.edit", "code.test", "git.diff"],
            expected_result="tested candidate patch and deterministic verification evidence",
            stop_conditions=["stop if repository subject version changes"],
            escalation_conditions=["promotion/deploy requires explicit current Decision and Authorization"],
            effect_class=EffectClass.INTERNAL_REVERSIBLE,
            fresh_until=now + timedelta(minutes=20),
        )
    if state is DeploymentHealthState.DEPLOYMENT_PROPOSED:
        return WorkProposal(
            id=f"proposal_deploy_effect_{assessment.id}",
            responsibility_ref=assessment.responsibility_ref,
            responsibility_version=assessment.responsibility_version,
            assessment_ref=assessment.id,
            subject_ref=assessment.subject_ref,
            work_kind="deployment-effect-proposal",
            title="Request bounded deployment effect",
            description=(
                "Represent requested deployment effect only; execution remains behind "
                "existing authorization/RealityBoundary."
            ),
            requested_resources=ResourceVector(
                compute_units=1,
                api_calls=1,
                human_attention_units=1,
                concurrency_slots=1,
            ),
            requested_capabilities=["deploy.request"],
            expected_result="authorized deployment request or explicit denial",
            stop_conditions=["stop if candidate version or deployment target changes"],
            escalation_conditions=["requires exact-scope current deployment authorization"],
            effect_class=EffectClass.EXTERNAL_EFFECT,
            fresh_until=now + timedelta(minutes=5),
        )
    return None


__all__ = [
    "DeploymentHealthState",
    "ListingIntegrityState",
    "assess_deployment_health",
    "assess_listing_integrity",
    "deployment_health_proposal",
    "listing_integrity_proposal",
]
