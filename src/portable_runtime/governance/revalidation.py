from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

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


class GovernanceLifecycleRejected(ValueError):
    """The current governance snapshot rejects the requested lifecycle step."""


@dataclass(frozen=True)
class RevalidationGovernanceResult:
    assessments: tuple[AffectedAssessment, ...]
    opened_obligations: tuple[ReviewObligation, ...]
    already_processed_obligation_ids: tuple[str, ...]


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
) -> ReviewObligation | None:
    """Project a revalidation policy disposition into one governance Q.

    Revalidation remains the owner of impact/risk/policy interpretation. This
    function creates no obligation for ``none`` or ``warn`` and never changes
    qualification or activation state.
    """

    action = _disposition(assessment)
    if action not in _REVIEW_ACTIONS:
        return None
    target = assessment.affected_ref
    if persistence.get_state(target) is None:
        return None
    invalidates = frozenset(
        decision.id
        for decision in persistence.list_decisions().values()
        if decision.target == target and decision.context == context
    )
    return ReviewObligation(
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
        blocking=action in _BLOCKING_ACTIONS,
        closure_requirements=_closure_requirements(action),
        invalidates_decisions=invalidates,
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
        for assessment in assessments:
            obligation = project_review_obligation(
                assessment,
                event_ref=event_ref,
                context=context,
                persistence=self.persistence,
            )
            if obligation is None:
                continue
            if _obligation_already_processed(self.persistence, obligation.id):
                processed.append(obligation.id)
                continue
            self.persistence.open_obligation(obligation)
            opened.append(obligation)
        return RevalidationGovernanceResult(
            assessments=assessments,
            opened_obligations=tuple(opened),
            already_processed_obligation_ids=tuple(processed),
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
