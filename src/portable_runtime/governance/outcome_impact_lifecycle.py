"""F1-B3 lifecycle from authoritative OutcomeConfirmed to existing ReviewObligation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from portable_runtime.governance.outcome_impact import (
    OutcomeConfirmedTriggerStore,
    OutcomeGovernanceDependency,
    resolve_outcome_confirmed_trigger,
)
from portable_runtime.governance.outcome_impact_commit import (
    CommittedOutcomeImpact,
    OutcomeDispositionPolicy,
    OutcomeImpactCommitRequest,
)
from portable_runtime.governance.outcome_impact_judgment import OutcomeImpactPolicy
from portable_runtime.governance.persistence import DistinctionGovernancePersistence
from portable_runtime.governance.revalidation import (
    ReviewProjection,
    project_review_obligation_from_disposition,
)
from portable_runtime.governance.distinction import ReviewObligation

OutcomeGovernanceImpactStatus = Literal[
    "processed",
    "already-processed",
    "not-declared",
    "unavailable",
]


class OutcomeImpactStateStore(OutcomeConfirmedTriggerStore, Protocol):
    def commit_outcome_impact_judgment(
        self,
        request: OutcomeImpactCommitRequest,
        impact_policy: OutcomeImpactPolicy,
        disposition_policy: OutcomeDispositionPolicy,
    ) -> CommittedOutcomeImpact: ...


ImpactPolicyResolver = Callable[[OutcomeGovernanceDependency], OutcomeImpactPolicy]
DispositionPolicyResolver = Callable[[OutcomeGovernanceDependency], OutcomeDispositionPolicy]


@dataclass(frozen=True)
class OutcomeGovernanceImpactResult:
    status: OutcomeGovernanceImpactStatus
    event_ref: str
    reason: str
    committed_impacts: tuple[CommittedOutcomeImpact, ...] = ()
    opened_obligations: tuple[ReviewObligation, ...] = ()
    already_processed_obligation_ids: tuple[str, ...] = ()
    projection_unavailable: tuple[ReviewProjection, ...] = ()


class OutcomeGovernanceImpactLifecycle:
    """Project verified Outcome governance consequences without crossing decision/application authority."""

    def __init__(
        self,
        *,
        store: OutcomeImpactStateStore,
        persistence: DistinctionGovernancePersistence,
    ) -> None:
        self.store = store
        self.persistence = persistence

    def observe_outcome_confirmed(
        self,
        *,
        event_ref: str,
        dependencies: tuple[OutcomeGovernanceDependency, ...],
        context: str,
        requested_scope: frozenset[str],
        subject_version_refs: tuple[str, ...],
        impact_policy_for: ImpactPolicyResolver,
        disposition_policy_for: DispositionPolicyResolver,
    ) -> OutcomeGovernanceImpactResult:
        """Resolve, judge, and atomically project one OutcomeConfirmed EventInstance into Q."""

        processed = self.persistence.processed_event_obligation_ids(event_ref)
        if processed is not None:
            return OutcomeGovernanceImpactResult(
                status="already-processed",
                event_ref=event_ref,
                reason="event-instance-already-processed",
                already_processed_obligation_ids=processed,
            )

        trigger = resolve_outcome_confirmed_trigger(self.store, event_ref)
        if not trigger.authoritative or trigger.outcome is None or trigger.accepted_event is None:
            return OutcomeGovernanceImpactResult(
                status="unavailable",
                event_ref=event_ref,
                reason=f"authoritative-trigger-{trigger.reason}",
            )
        if not dependencies:
            return OutcomeGovernanceImpactResult(
                status="not-declared",
                event_ref=event_ref,
                reason="explicit-outcome-governance-dependency-absent",
            )

        seen_targets: set[tuple[str, str]] = set()
        committed: list[CommittedOutcomeImpact] = []
        ready: list[ReviewObligation] = []
        unavailable: list[ReviewProjection] = []
        for dependency in dependencies:
            target_key = (dependency.scheme_id, dependency.context)
            if target_key in seen_targets:
                return OutcomeGovernanceImpactResult(
                    status="unavailable",
                    event_ref=event_ref,
                    reason="duplicate-outcome-governance-target",
                    committed_impacts=tuple(committed),
                )
            seen_targets.add(target_key)
            request = OutcomeImpactCommitRequest(
                event_ref=event_ref,
                dependency=dependency,
                context=context,
                requested_scope=requested_scope,
                subject_version_refs=subject_version_refs,
            )
            try:
                impact = self.store.commit_outcome_impact_judgment(
                    request,
                    impact_policy_for(dependency),
                    disposition_policy_for(dependency),
                )
            except (ValueError, RuntimeError) as exc:
                return OutcomeGovernanceImpactResult(
                    status="unavailable",
                    event_ref=event_ref,
                    reason=f"impact-commit-unavailable:{exc}",
                    committed_impacts=tuple(committed),
                )
            committed.append(impact)

            if impact.judgment.impact in {"no-governance-impact", "recovery-only"}:
                if impact.disposition.action not in {"none", "warn"}:
                    return OutcomeGovernanceImpactResult(
                        status="unavailable",
                        event_ref=event_ref,
                        reason="non-governance-impact-has-review-disposition",
                        committed_impacts=tuple(committed),
                    )
                continue

            basis_refs = tuple(
                dict.fromkeys(
                    (
                        trigger.outcome.id,
                        trigger.accepted_event.id,
                        impact.judgment_event_ref,
                        *dependency.basis_refs,
                        impact.disposition_event_ref,
                        impact.disposition.policy_ref,
                    )
                )
            )
            projection = project_review_obligation_from_disposition(
                trigger_event_ref=event_ref,
                target=dependency.scheme_id,
                context=dependency.context,
                disposition=impact.disposition,
                basis_refs=basis_refs,
                persistence=self.persistence,
            )
            if projection.status == "not-required":
                continue
            if projection.status == "projection-unavailable":
                unavailable.append(projection)
                continue
            if projection.obligation is None:
                return OutcomeGovernanceImpactResult(
                    status="unavailable",
                    event_ref=event_ref,
                    reason="ready-review-projection-without-obligation",
                    committed_impacts=tuple(committed),
                )
            ready.append(projection.obligation)

        if unavailable:
            return OutcomeGovernanceImpactResult(
                status="unavailable",
                event_ref=event_ref,
                reason="review-projection-unavailable",
                committed_impacts=tuple(committed),
                projection_unavailable=tuple(unavailable),
            )

        committed_ids = self.persistence.commit_event_obligations(event_ref, tuple(ready))
        opened = tuple(obligation for obligation in ready if obligation.id in committed_ids)
        return OutcomeGovernanceImpactResult(
            status="processed",
            event_ref=event_ref,
            reason="outcome-governance-impact-projected",
            committed_impacts=tuple(committed),
            opened_obligations=opened,
        )


__all__ = [
    "DispositionPolicyResolver",
    "ImpactPolicyResolver",
    "OutcomeGovernanceImpactLifecycle",
    "OutcomeGovernanceImpactResult",
    "OutcomeGovernanceImpactStatus",
    "OutcomeImpactStateStore",
]
