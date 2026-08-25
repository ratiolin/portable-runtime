from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from portable_runtime.governance.distinction import (
    ApplicationReceipt,
    AuthorityCheck,
    FreshnessAnchorLookup,
    GovernanceConfiguration,
    GovernanceDecision,
    GovernanceRuntime,
    GovernedApplication,
    ReviewObligation,
    apply_review_discharge,
    apply_state_transition,
    record_decision,
    usable,
)
from portable_runtime.governance.persistence import DistinctionGovernancePersistence
from portable_runtime.records.revalidation import (
    DEFAULT_REVALIDATION_POLICY_PROFILE,
    AffectedAssessment,
    DefaultRevalidationPolicyProfile,
    ImpactType,
    assess_revalidation,
)

_REVIEW_ACTIONS = frozenset(
    {
        "background-revalidate",
        "block-next-use",
        "require-human-review",
        "reopen",
    }
)
_BLOCKING_ACTIONS = frozenset(
    {
        "block-next-use",
        "require-human-review",
        "reopen",
    }
)

ProjectionStatus = Literal["not-required", "ready", "projection-unavailable"]


class GovernanceLifecycleRejected(ValueError):
    """The current governance snapshot rejects the requested lifecycle step."""


@dataclass(frozen=True)
class ReviewProjection:
    """Structured result of projecting one policy disposition into governance state."""

    status: ProjectionStatus
    action: ImpactType
    target: str
    blocking: bool
    obligation: ReviewObligation | None = None


class GovernanceProjectionUnavailable(GovernanceLifecycleRejected):
    """A review responsibility cannot be represented by the governance projection."""

    def __init__(self, projection: ReviewProjection) -> None:
        self.projection = projection
        super().__init__(
            f"governance projection unavailable for {projection.target!r} "
            f"under {projection.action!r} disposition"
        )


@dataclass(frozen=True)
class RevalidationGovernanceResult:
    assessments: tuple[AffectedAssessment, ...]
    opened_obligations: tuple[ReviewObligation, ...]
    already_processed_obligation_ids: tuple[str, ...]
    projection_unavailable: tuple[ReviewProjection, ...] = ()


def _disposition(assessment: AffectedAssessment) -> ImpactType:
    if assessment.revalidation_disposition is not None:
        return assessment.revalidation_disposition.action
    return assessment.required_action


def _obligation_id(
    *,
    event_ref: str,
    target: str,
    context: str,
    action: ImpactType,
) -> str:
    # Phase D compatibility identity. Phase D.5 will move replay ownership to
    # the durable EventInstance processor rather than deriving it from Q.
    material = "\x1f".join((event_ref, target, context, action)).encode()
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f"review_{digest}"


def _closure_requirements(action: ImpactType) -> frozenset[str]:
    requirements = {"basis_checked"}
    if action == "require-human-review":
        requirements.add("human_reviewed")
    if action == "reopen":
        requirements.add("reopen_resolved")
    return frozenset(requirements)


def _snapshot(persistence: DistinctionGovernancePersistence) -> GovernanceConfiguration:
    return GovernanceConfiguration(
        states=persistence.list_states(),
        runtime=GovernanceRuntime(
            obligations=persistence.list_obligations(),
            decisions=persistence.list_decisions(),
            applications=persistence.list_applications(),
        ),
    )


def _obligation_already_processed(
    persistence: DistinctionGovernancePersistence,
    obligation_id: str,
) -> bool:
    if persistence.get_obligation(obligation_id) is not None:
        return True
    return any(
        receipt.application.review_obligation_id == obligation_id
        for receipt in persistence.list_applications().values()
    )


def project_review_obligation(
    assessment: AffectedAssessment,
    *,
    event_ref: str,
    context: str,
    persistence: DistinctionGovernancePersistence,
) -> ReviewProjection:
    """Project a policy disposition into a structured governance result.

    Revalidation remains the owner of impact/risk/policy interpretation. This
    function never changes qualification or activation. Missing representation
    is explicit rather than collapsing into the same result as ``no review``.
    """

    action = _disposition(assessment)
    target = assessment.affected_ref
    blocking = action in _BLOCKING_ACTIONS
    if action not in _REVIEW_ACTIONS:
        return ReviewProjection(
            status="not-required",
            action=action,
            target=target,
            blocking=False,
        )
    if persistence.get_state(target) is None:
        return ReviewProjection(
            status="projection-unavailable",
            action=action,
            target=target,
            blocking=blocking,
        )
    invalidates = frozenset(
        decision.id
        for decision in persistence.list_decisions().values()
        if decision.target == target and decision.context == context
    )
    obligation = ReviewObligation(
        id=_obligation_id(
            event_ref=event_ref,
            target=target,
            context=context,
            action=action,
        ),
        target=target,
        trigger_ref=event_ref,
        basis_refs=(assessment.change_ref,),
        context=context,
        blocking=blocking,
        closure_requirements=_closure_requirements(action),
        invalidates_decisions=invalidates,
    )
    return ReviewProjection(
        status="ready",
        action=action,
        target=target,
        blocking=blocking,
        obligation=obligation,
    )


class RevalidationGovernanceLifecycle:
    """Internal bridge from revalidation policy output to governed review state.

    The bridge deliberately does not own dependency detection, policy rules,
    provider execution, or RealityBoundary admission.
    """

    def __init__(
        self,
        *,
        persistence: DistinctionGovernancePersistence,
        authority: AuthorityCheck,
        freshness: FreshnessAnchorLookup,
    ) -> None:
        self.persistence = persistence
        self.authority = authority
        self.freshness = freshness

    def snapshot(self) -> GovernanceConfiguration:
        return _snapshot(self.persistence)

    def is_usable(self, scheme_id: str, context: str) -> bool:
        return usable(self.snapshot(), scheme_id, context)

    def observe_change(
        self,
        *,
        event_ref: str,
        change_ref: str,
        change_type: str,
        relations: list[Any],
        context: str,
        profile: DefaultRevalidationPolicyProfile = DEFAULT_REVALIDATION_POLICY_PROFILE,
    ) -> RevalidationGovernanceResult:
        """Detect direct impacts and open only the review obligations policy requires."""

        if not event_ref:
            raise ValueError("event_ref must be non-empty")
        assessments = tuple(
            assess_revalidation(
                change_ref,
                change_type,
                relations,
                profile=profile,
            )
        )
        opened: list[ReviewObligation] = []
        processed: list[str] = []
        unavailable: list[ReviewProjection] = []
        for assessment in assessments:
            projection = project_review_obligation(
                assessment,
                event_ref=event_ref,
                context=context,
                persistence=self.persistence,
            )
            if projection.status == "not-required":
                continue
            if projection.status == "projection-unavailable":
                unavailable.append(projection)
                if projection.blocking:
                    raise GovernanceProjectionUnavailable(projection)
                continue
            obligation = projection.obligation
            if obligation is None:
                raise GovernanceLifecycleRejected("ready governance projection requires an obligation")
            if _obligation_already_processed(self.persistence, obligation.id):
                processed.append(obligation.id)
                continue
            self.persistence.open_obligation(obligation)
            opened.append(obligation)
        return RevalidationGovernanceResult(
            assessments=assessments,
            opened_obligations=tuple(opened),
            already_processed_obligation_ids=tuple(processed),
            projection_unavailable=tuple(unavailable),
        )

    def record_decision(self, decision: GovernanceDecision) -> None:
        config = self.snapshot()
        admitted = record_decision(config, decision, self.authority)
        if admitted is None:
            raise GovernanceLifecycleRejected(
                "governance decision is not admissible under the current review snapshot"
            )
        self.persistence.record_decision(decision)

    def apply_state(self, application: GovernedApplication) -> ApplicationReceipt:
        config = self.snapshot()
        admitted = apply_state_transition(
            config,
            application,
            self.authority,
            self.freshness,
        )
        if admitted is None:
            raise GovernanceLifecycleRejected(
                "governed state application is not admissible under the current snapshot"
            )
        receipt = admitted.runtime.applications[application.id]
        next_state = admitted.states[application.scheme_id]
        self.persistence.commit_state_application(
            application.scheme_id,
            next_state,
            receipt,
        )
        return receipt

    def discharge(
        self,
        application: GovernedApplication,
        *,
        state_application: GovernedApplication | None = None,
    ) -> ApplicationReceipt:
        config = self.snapshot()
        admitted = apply_review_discharge(
            config,
            application,
            self.authority,
            self.freshness,
            state_application,
        )
        if admitted is None:
            raise GovernanceLifecycleRejected(
                "review discharge is not admissible under the current snapshot"
            )
        receipt = admitted.runtime.applications[application.id]
        obligation_id = application.review_obligation_id
        if obligation_id is None:
            raise GovernanceLifecycleRejected(
                "review discharge requires an explicit obligation reference"
            )
        self.persistence.commit_review_discharge(obligation_id, receipt)
        return receipt
