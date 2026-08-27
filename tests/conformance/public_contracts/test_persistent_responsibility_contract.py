from __future__ import annotations

from datetime import UTC, datetime

from portable_runtime.responsibility import (
    DeploymentHealthState,
    EffectClass,
    ListingIntegrityState,
    ResponsibilityAdmission,
    ResponsibilityKernel,
    ResponsibilityStatus,
    StandingResponsibility,
    assess_deployment_health,
    assess_listing_integrity,
    deployment_health_proposal,
    inspect_responsibility,
    listing_integrity_proposal,
)
from portable_runtime.stores.memory import InMemoryStateStore


def _now() -> datetime:
    return datetime(2026, 8, 27, 7, 0, tzinfo=UTC)


def _register(
    kernel: ResponsibilityKernel,
    *,
    responsibility_id: str,
    kind: str,
    statement: str,
    scope: dict[str, str],
) -> None:
    kernel.register(
        StandingResponsibility(
            id=responsibility_id,
            responsibility_kind=kind,
            statement=statement,
            scope=scope,
        ),
        ResponsibilityAdmission(
            id=f"admission_{responsibility_id}",
            responsibility_ref=responsibility_id,
            principal_ref="principal:owner",
            basis_refs=[f"decision:admit:{responsibility_id}"],
        ),
    )


def test_commerce_health_assessment_does_not_create_work() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(
        kernel,
        responsibility_id="sr_listing_integrity",
        kind="commerce-listing-integrity",
        statement="Maintain Shopify listing integrity",
        scope={"shop": "dev", "channel": "online-store"},
    )
    assessment = assess_listing_integrity(
        kernel,
        responsibility_ref="sr_listing_integrity",
        subject_ref="shopify:product:1",
        state=ListingIntegrityState.HEALTH_VERIFIED,
        evidence_refs=["commerce-readback:1", "shopify-readback:1"],
        now=_now(),
    )

    proposal = listing_integrity_proposal(
        assessment,
        state=ListingIntegrityState.HEALTH_VERIFIED,
        now=_now(),
    )

    assert proposal is None
    assert store.list_work() == []
    assert kernel.current_status("sr_listing_integrity") is ResponsibilityStatus.ACTIVE


def test_commerce_drift_creates_diagnosis_proposal_not_external_authority() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(
        kernel,
        responsibility_id="sr_listing_integrity",
        kind="commerce-listing-integrity",
        statement="Maintain Shopify listing integrity",
        scope={"shop": "dev", "channel": "online-store"},
    )
    assessment = assess_listing_integrity(
        kernel,
        responsibility_ref="sr_listing_integrity",
        subject_ref="shopify:product:1",
        state=ListingIntegrityState.DRIFT_DETECTED,
        evidence_refs=["commerce-revision:7", "shopify-readback:7"],
        now=_now(),
    )
    proposal = listing_integrity_proposal(
        assessment,
        state=ListingIntegrityState.DRIFT_DETECTED,
        now=_now(),
    )

    assert proposal is not None
    assert proposal.effect_class is EffectClass.READ_ONLY
    kernel.propose(proposal, now=_now())
    assert store.list_work() == []
    assert store.list_authorizations() == []


def test_service_health_verified_does_not_create_repair_work() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(
        kernel,
        responsibility_id="sr_deployment_health",
        kind="service-deployment-health",
        statement="Maintain deployment health",
        scope={"service": "control-plane", "environment": "personal"},
    )
    assessment = assess_deployment_health(
        kernel,
        responsibility_ref="sr_deployment_health",
        subject_ref="service:control-plane",
        state=DeploymentHealthState.HEALTH_VERIFIED,
        evidence_refs=["promql:ready", "probe:http:ready"],
        now=_now(),
    )

    proposal = deployment_health_proposal(
        assessment,
        state=DeploymentHealthState.HEALTH_VERIFIED,
        now=_now(),
    )

    assert proposal is None
    assert store.list_work() == []
    assert kernel.current_status("sr_deployment_health") is ResponsibilityStatus.ACTIVE


def test_service_candidate_patch_and_deploy_request_keep_effect_boundaries_distinct() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(
        kernel,
        responsibility_id="sr_deployment_health",
        kind="service-deployment-health",
        statement="Maintain deployment health",
        scope={"service": "control-plane", "environment": "personal"},
    )
    candidate_assessment = assess_deployment_health(
        kernel,
        responsibility_ref="sr_deployment_health",
        subject_ref="repo:control-plane@abc123",
        state=DeploymentHealthState.CANDIDATE_CHANGE_NEEDED,
        evidence_refs=["diagnosis:incident-1"],
        now=_now(),
    )
    candidate = deployment_health_proposal(
        candidate_assessment,
        state=DeploymentHealthState.CANDIDATE_CHANGE_NEEDED,
        now=_now(),
    )
    assert candidate is not None
    assert candidate.effect_class is EffectClass.INTERNAL_REVERSIBLE
    kernel.propose(candidate, now=_now())

    deploy_assessment = assess_deployment_health(
        kernel,
        responsibility_ref="sr_deployment_health",
        subject_ref="candidate:abc123",
        state=DeploymentHealthState.DEPLOYMENT_PROPOSED,
        evidence_refs=["candidate:test-passed", "candidate:diff-reviewed"],
        now=_now(),
    )
    deploy = deployment_health_proposal(
        deploy_assessment,
        state=DeploymentHealthState.DEPLOYMENT_PROPOSED,
        now=_now(),
    )
    assert deploy is not None
    assert deploy.effect_class is EffectClass.EXTERNAL_EFFECT
    kernel.propose(deploy, now=_now())

    assert store.list_work() == []
    assert store.list_authorizations() == []
    assert kernel.current_status("sr_deployment_health") is ResponsibilityStatus.ACTIVE


def test_operator_inspection_is_non_authority_bearing() -> None:
    store = InMemoryStateStore()
    kernel = ResponsibilityKernel(store)
    _register(
        kernel,
        responsibility_id="sr_listing_integrity",
        kind="commerce-listing-integrity",
        statement="Maintain Shopify listing integrity",
        scope={"shop": "dev"},
    )

    projection = inspect_responsibility(kernel, "sr_listing_integrity", now=_now())

    assert projection.authority_bearing is False
    assert projection.status is ResponsibilityStatus.ACTIVE
    assert projection.principal_ref == "principal:owner"
    assert store.list_authorizations() == []
