from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from portable_runtime.core.models import Work
from portable_runtime.responsibility.models import (
    Commitment,
    ContinuityValidation,
    ExpectationResolutionKind,
    PortfolioAdmissionDecision,
    PriorityJudgment,
    ReasoningSessionBinding,
    ResourcePool,
    ResourceReservation,
    ResourceReservationRelease,
    ResourceVector,
    ResponsibilityAdmission,
    ResponsibilityAssessment,
    ResponsibilityContextSnapshot,
    ResponsibilityExpectation,
    ResponsibilityExpectationResolution,
    ResponsibilityHandoff,
    ResponsibilityLifecycleTransition,
    ResponsibilityObject,
    ResponsibilityRevision,
    ResponsibilityStatus,
    StandingResponsibility,
    WorkProposal,
)
from portable_runtime.responsibility.persistence import ResponsibilityJournal


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:32]}"


def _semantic_dump(value: Any) -> dict[str, object]:
    raw = value.model_dump(mode="json")
    if isinstance(raw, dict):
        raw = dict(raw)
        raw.pop("created_at", None)
    return raw


class ResponsibilityKernel:
    """Durable coordination kernel for persistent responsibility.

    The kernel can create bounded Work, but it never mints execution
    authorization and never interprets provider success as responsibility
    discharge. External effects remain behind the existing runtime authority
    and RealityBoundary path.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self.journal = ResponsibilityJournal(store)

    def _list(
        self,
        object_type: str | None = None,
        responsibility_ref: str | None = None,
    ) -> list[ResponsibilityObject]:
        return self.journal.list(object_type, responsibility_ref)

    def _get(self, object_id: str, expected_type: type[Any] | None = None) -> Any:
        value = self.journal.get(object_id)
        if value is None:
            raise ValueError(f"unknown responsibility object: {object_id}")
        if expected_type is not None and not isinstance(value, expected_type):
            raise ValueError(
                f"responsibility object {object_id!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        return value

    def _save_append_only(self, value: ResponsibilityObject) -> ResponsibilityObject:
        existing = self.journal.get(value.id)
        if existing is not None:
            if _semantic_dump(existing) == _semantic_dump(value):
                return existing
            raise ValueError(f"responsibility object {value.id!r} is append-only")
        return self.journal.save(value)

    def get_responsibility(self, responsibility_id: str) -> StandingResponsibility:
        return self._get(responsibility_id, StandingResponsibility)

    def current_definition(self, responsibility_id: str) -> tuple[int, str, dict[str, str]]:
        identity = self.get_responsibility(responsibility_id)
        version = 1
        statement = identity.statement
        scope = dict(identity.scope)
        revisions = sorted(
            (
                value
                for value in self._list("ResponsibilityRevision", responsibility_id)
                if isinstance(value, ResponsibilityRevision)
            ),
            key=lambda value: value.to_version,
        )
        for revision in revisions:
            if revision.from_version != version:
                raise ValueError("responsibility revision history is not contiguous")
            version = revision.to_version
            statement = revision.statement
            scope = dict(revision.scope)
        return version, statement, scope

    def current_status(self, responsibility_id: str) -> ResponsibilityStatus:
        self.get_responsibility(responsibility_id)
        admissions = [
            value
            for value in self._list("ResponsibilityAdmission", responsibility_id)
            if isinstance(value, ResponsibilityAdmission)
        ]
        if not admissions:
            raise ValueError("standing responsibility is not admitted")
        status = ResponsibilityStatus.ACTIVE
        transitions = sorted(
            (
                value
                for value in self._list("ResponsibilityLifecycleTransition", responsibility_id)
                if isinstance(value, ResponsibilityLifecycleTransition)
            ),
            key=lambda value: (value.applied_at, value.id),
        )
        for transition in transitions:
            if transition.from_status is not status:
                raise ValueError("responsibility lifecycle history is not contiguous")
            status = transition.to_status
        return status

    def register(
        self,
        identity: StandingResponsibility,
        admission: ResponsibilityAdmission,
    ) -> StandingResponsibility:
        if admission.responsibility_ref != identity.id:
            raise ValueError("admission must bind the standing responsibility identity")
        if admission.responsibility_version != 1:
            raise ValueError("initial responsibility admission must bind version 1")
        if not admission.principal_ref.strip():
            raise ValueError("responsibility admission requires principal_ref")
        with self.store.transaction():
            if self.journal.get(identity.id) is not None:
                raise ValueError(f"standing responsibility already exists: {identity.id}")
            self.journal.save(identity)
            self._save_append_only(admission)
        return identity

    def revise(self, revision: ResponsibilityRevision) -> ResponsibilityRevision:
        current_version, _statement, _scope = self.current_definition(revision.responsibility_ref)
        if revision.from_version != current_version:
            raise ValueError("responsibility revision is stale")
        if self.current_status(revision.responsibility_ref) is ResponsibilityStatus.DISCHARGED:
            raise ValueError("discharged responsibility must be explicitly reopened before revision")
        return self._save_append_only(revision)  # type: ignore[return-value]

    def transition(
        self,
        transition: ResponsibilityLifecycleTransition,
    ) -> ResponsibilityLifecycleTransition:
        current_version, _statement, _scope = self.current_definition(transition.responsibility_ref)
        if transition.responsibility_version != current_version:
            raise ValueError("responsibility lifecycle transition is stale")
        if transition.from_status is not self.current_status(transition.responsibility_ref):
            raise ValueError("responsibility lifecycle transition has stale from_status")
        return self._save_append_only(transition)  # type: ignore[return-value]

    def create_expectation(
        self,
        expectation: ResponsibilityExpectation,
    ) -> ResponsibilityExpectation:
        current_version, _statement, _scope = self.current_definition(expectation.responsibility_ref)
        if self.current_status(expectation.responsibility_ref) is not ResponsibilityStatus.ACTIVE:
            raise ValueError("expectation requires an active standing responsibility")
        if expectation.responsibility_version != current_version:
            raise ValueError("expectation is bound to a stale responsibility version")
        return self._save_append_only(expectation)  # type: ignore[return-value]

    def expectation_open(self, expectation_id: str) -> bool:
        expectation = self._get(expectation_id, ResponsibilityExpectation)
        resolutions = [
            value
            for value in self._list("ResponsibilityExpectationResolution", expectation.responsibility_ref)
            if isinstance(value, ResponsibilityExpectationResolution)
            and value.expectation_ref == expectation_id
        ]
        return not resolutions

    def resolve_expectation(
        self,
        resolution: ResponsibilityExpectationResolution,
    ) -> ResponsibilityExpectationResolution:
        expectation = self._get(resolution.expectation_ref, ResponsibilityExpectation)
        if expectation.responsibility_ref != resolution.responsibility_ref:
            raise ValueError("expectation resolution responsibility mismatch")
        if not self.expectation_open(expectation.id):
            existing = [
                value
                for value in self._list("ResponsibilityExpectationResolution", expectation.responsibility_ref)
                if isinstance(value, ResponsibilityExpectationResolution)
                and value.expectation_ref == expectation.id
            ]
            if len(existing) == 1 and _semantic_dump(existing[0]) == _semantic_dump(resolution):
                return existing[0]
            raise ValueError("expectation is already resolved")
        return self._save_append_only(resolution)  # type: ignore[return-value]

    def assess_due_expectation(
        self,
        expectation_id: str,
        *,
        now: datetime,
        observed_evidence_refs: list[str] | tuple[str, ...],
    ) -> ResponsibilityAssessment | None:
        expectation = self._get(expectation_id, ResponsibilityExpectation)
        if not self.expectation_open(expectation.id):
            return None
        current_version, _statement, _scope = self.current_definition(expectation.responsibility_ref)
        if expectation.responsibility_version != current_version:
            raise ValueError("stale expectation requires revalidation before assessment")
        if self.current_status(expectation.responsibility_ref) is not ResponsibilityStatus.ACTIVE:
            return None
        observed = [str(ref) for ref in observed_evidence_refs if str(ref).strip()]
        if observed:
            resolution = ResponsibilityExpectationResolution(
                id=_stable_id("expectation_resolution", expectation.id, "satisfied"),
                expectation_ref=expectation.id,
                responsibility_ref=expectation.responsibility_ref,
                resolution=ExpectationResolutionKind.SATISFIED,
                basis_refs=observed,
                resolved_at=now,
            )
            self.resolve_expectation(resolution)
            return None
        if now < expectation.due_at:
            return None
        assessment_id = _stable_id("assessment", expectation.id, expectation.due_at.isoformat(), "missing")
        existing = self.journal.get(assessment_id)
        if existing is not None:
            if not isinstance(existing, ResponsibilityAssessment):
                raise ValueError("deterministic assessment identity rebound")
            return existing
        fresh_until = None
        if expectation.freshness_window_seconds is not None:
            fresh_until = now + timedelta(seconds=expectation.freshness_window_seconds)
        assessment = ResponsibilityAssessment(
            id=assessment_id,
            responsibility_ref=expectation.responsibility_ref,
            responsibility_version=current_version,
            subject_ref=expectation.subject_ref,
            assessment_kind="expected-signal-missing",
            basis_refs=[expectation.id],
            assessed_at=now,
            fresh_until=fresh_until,
            rationale=f"expected {expectation.expected_signal_kind} evidence is absent after due_at",
        )
        return self._save_append_only(assessment)  # type: ignore[return-value]

    def propose(self, proposal: WorkProposal, *, now: datetime) -> WorkProposal:
        current_version, _statement, _scope = self.current_definition(proposal.responsibility_ref)
        if self.current_status(proposal.responsibility_ref) is not ResponsibilityStatus.ACTIVE:
            raise ValueError("work proposal requires an active standing responsibility")
        if proposal.responsibility_version != current_version:
            raise ValueError("historical proposal cannot enter current admission")
        assessment = self._get(proposal.assessment_ref, ResponsibilityAssessment)
        if assessment.responsibility_ref != proposal.responsibility_ref:
            raise ValueError("proposal assessment belongs to another responsibility")
        if assessment.responsibility_version != current_version:
            raise ValueError("proposal assessment is stale")
        if assessment.fresh_until is not None and now > assessment.fresh_until:
            raise ValueError("proposal assessment is no longer fresh")
        if proposal.fresh_until is not None and now > proposal.fresh_until:
            raise ValueError("proposal is already stale")
        return self._save_append_only(proposal)  # type: ignore[return-value]

    def record_priority_judgment(self, judgment: PriorityJudgment) -> PriorityJudgment:
        self._get(judgment.proposal_ref, WorkProposal)
        if not judgment.policy_ref.strip():
            raise ValueError("priority judgment requires explicit versioned policy_ref")
        return self._save_append_only(judgment)  # type: ignore[return-value]

    def create_resource_pool(self, pool: ResourcePool) -> ResourcePool:
        if not pool.policy_ref.strip():
            raise ValueError("resource pool requires explicit versioned policy_ref")
        return self._save_append_only(pool)  # type: ignore[return-value]

    def record_portfolio_admission(
        self,
        decision: PortfolioAdmissionDecision,
    ) -> PortfolioAdmissionDecision:
        proposal = self._get(decision.proposal_ref, WorkProposal)
        pool = self._get(decision.resource_pool_ref, ResourcePool)
        if decision.policy_ref != pool.policy_ref:
            raise ValueError("portfolio admission policy must match resource pool policy")
        if decision.admitted and not proposal.requested_resources.fits_within(pool.capacity):
            raise ValueError("portfolio admission cannot admit a request larger than pool capacity")
        return self._save_append_only(decision)  # type: ignore[return-value]

    def _reservation_released(self, reservation: ResourceReservation, *, now: datetime) -> bool:
        releases = [
            value
            for value in self._list("ResourceReservationRelease", reservation.responsibility_ref)
            if isinstance(value, ResourceReservationRelease)
            and value.reservation_ref == reservation.id
        ]
        if releases:
            return True
        return reservation.expires_at is not None and reservation.expires_at <= now

    def available_resources(self, resource_pool_ref: str, *, now: datetime) -> ResourceVector:
        pool = self._get(resource_pool_ref, ResourcePool)
        used = ResourceVector()
        for value in self._list("ResourceReservation"):
            if not isinstance(value, ResourceReservation):
                continue
            if value.resource_pool_ref != pool.id or self._reservation_released(value, now=now):
                continue
            used = used.plus(value.resources)
        available_domain = {
            key: max(0, value - used.domain_quota.get(key, 0))
            for key, value in pool.capacity.domain_quota.items()
        }
        return ResourceVector(
            compute_units=max(0, pool.capacity.compute_units - used.compute_units),
            api_calls=max(0, pool.capacity.api_calls - used.api_calls),
            money_minor=max(0, pool.capacity.money_minor - used.money_minor),
            human_attention_units=max(0, pool.capacity.human_attention_units - used.human_attention_units),
            concurrency_slots=max(0, pool.capacity.concurrency_slots - used.concurrency_slots),
            domain_quota=available_domain,
        )

    def reserve(
        self,
        reservation: ResourceReservation,
        *,
        now: datetime,
    ) -> ResourceReservation:
        proposal = self._get(reservation.proposal_ref, WorkProposal)
        if proposal.responsibility_ref != reservation.responsibility_ref:
            raise ValueError("reservation/proposal responsibility mismatch")
        if proposal.requested_resources != reservation.resources:
            raise ValueError("reservation must exactly bind proposal resource request")
        with self.store.transaction():
            available = self.available_resources(reservation.resource_pool_ref, now=now)
            if not reservation.resources.fits_within(available):
                raise ValueError("resource reservation would overcommit the pool")
            return self._save_append_only(reservation)  # type: ignore[return-value]

    def release_reservation(
        self,
        release: ResourceReservationRelease,
    ) -> ResourceReservationRelease:
        reservation = self._get(release.reservation_ref, ResourceReservation)
        if reservation.responsibility_ref != release.responsibility_ref:
            raise ValueError("reservation release responsibility mismatch")
        existing = [
            value
            for value in self._list("ResourceReservationRelease", release.responsibility_ref)
            if isinstance(value, ResourceReservationRelease)
            and value.reservation_ref == reservation.id
        ]
        if existing:
            if len(existing) == 1 and _semantic_dump(existing[0]) == _semantic_dump(release):
                return existing[0]
            raise ValueError("reservation already released")
        return self._save_append_only(release)  # type: ignore[return-value]

    def commit(
        self,
        commitment: Commitment,
        *,
        now: datetime,
    ) -> Commitment:
        proposal = self._get(commitment.proposal_ref, WorkProposal)
        priority = self._get(commitment.priority_judgment_ref, PriorityJudgment)
        portfolio = self._get(commitment.portfolio_admission_ref, PortfolioAdmissionDecision)
        reservation = self._get(commitment.reservation_ref, ResourceReservation)
        current_version, _statement, _scope = self.current_definition(commitment.responsibility_ref)
        if self.current_status(commitment.responsibility_ref) is not ResponsibilityStatus.ACTIVE:
            raise ValueError("commitment requires active standing responsibility")
        if commitment.responsibility_version != current_version:
            raise ValueError("commitment is bound to stale responsibility version")
        if proposal.responsibility_ref != commitment.responsibility_ref:
            raise ValueError("proposal/commitment responsibility mismatch")
        if proposal.responsibility_version != current_version:
            raise ValueError("historical proposal cannot be committed")
        if proposal.fresh_until is not None and now > proposal.fresh_until:
            raise ValueError("stale proposal cannot be committed")
        assessment = self._get(proposal.assessment_ref, ResponsibilityAssessment)
        if assessment.fresh_until is not None and now > assessment.fresh_until:
            raise ValueError("stale assessment cannot be committed")
        if priority.proposal_ref != proposal.id or not priority.admitted:
            raise ValueError("commitment requires an admitted priority judgment")
        if portfolio.proposal_ref != proposal.id or not portfolio.admitted:
            raise ValueError("commitment requires portfolio admission")
        if reservation.proposal_ref != proposal.id:
            raise ValueError("commitment reservation must bind the proposal")
        if self._reservation_released(reservation, now=now):
            raise ValueError("commitment reservation is not current")
        if commitment.resources != proposal.requested_resources or commitment.resources != reservation.resources:
            raise ValueError("commitment resources must exactly bind proposal and reservation")
        return self._save_append_only(commitment)  # type: ignore[return-value]

    def materialize_work(self, commitment_id: str) -> Work:
        commitment = self._get(commitment_id, Commitment)
        proposal = self._get(commitment.proposal_ref, WorkProposal)
        work_id = _stable_id("work", commitment.id, proposal.id)
        existing = self.store.get_work(work_id)
        metadata = {
            "standing_responsibility_ref": commitment.responsibility_ref,
            "standing_responsibility_version": commitment.responsibility_version,
            "responsibility_proposal_ref": proposal.id,
            "responsibility_commitment_ref": commitment.id,
            "responsibility_reservation_ref": commitment.reservation_ref,
            "persistent_responsibility_contract": "persistent-responsibility-v1",
            "effect_class": proposal.effect_class.value,
            "external_effect_authority": "required-separately",
        }
        work = Work(
            id=work_id,
            kind=proposal.work_kind,
            title=proposal.title,
            description=proposal.description,
            status="open",
            constraints={
                "responsibility_stop_conditions": list(proposal.stop_conditions),
                "responsibility_escalation_conditions": list(proposal.escalation_conditions),
            },
            acceptance_criteria=[proposal.expected_result] if proposal.expected_result else [],
            requested_capabilities=list(proposal.requested_capabilities),
            metadata=metadata,
        )
        if existing is not None:
            if _semantic_dump(existing) != _semantic_dump(work):
                raise ValueError("deterministic responsibility Work identity rebound")
            return existing
        self.store.save_work(work)
        return work

    def bind_reasoning_session(self, binding: ReasoningSessionBinding) -> ReasoningSessionBinding:
        current_version, _statement, _scope = self.current_definition(binding.responsibility_ref)
        if binding.responsibility_version != current_version:
            raise ValueError("reasoning session binding is stale")
        return self._save_append_only(binding)  # type: ignore[return-value]

    def create_context_snapshot(
        self,
        responsibility_id: str,
        *,
        unresolved_unknowns: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        qualification_dependency_refs: list[str] | None = None,
        reopen_conditions: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        escalation_conditions: list[str] | None = None,
    ) -> ResponsibilityContextSnapshot:
        version, _statement, scope = self.current_definition(responsibility_id)
        expectations = [
            value
            for value in self._list("ResponsibilityExpectation", responsibility_id)
            if isinstance(value, ResponsibilityExpectation) and self.expectation_open(value.id)
        ]
        assessments = [
            value
            for value in self._list("ResponsibilityAssessment", responsibility_id)
            if isinstance(value, ResponsibilityAssessment)
        ]
        proposals = [
            value
            for value in self._list("WorkProposal", responsibility_id)
            if isinstance(value, WorkProposal) and value.responsibility_version == version
        ]
        commitments = [
            value
            for value in self._list("Commitment", responsibility_id)
            if isinstance(value, Commitment) and value.responsibility_version == version
        ]
        reservations = [
            value
            for value in self._list("ResourceReservation", responsibility_id)
            if isinstance(value, ResourceReservation)
        ]
        work_refs = [
            work.id
            for work in self.store.list_work()
            if isinstance(work.metadata, dict)
            and work.metadata.get("standing_responsibility_ref") == responsibility_id
        ]
        snapshot = ResponsibilityContextSnapshot(
            id=_stable_id(
                "responsibility_context",
                responsibility_id,
                version,
                len(expectations),
                len(assessments),
                len(proposals),
                len(commitments),
                len(work_refs),
            ),
            responsibility_ref=responsibility_id,
            responsibility_version=version,
            scope=scope,
            open_expectation_refs=[value.id for value in expectations],
            open_assessment_refs=[value.id for value in assessments],
            unresolved_unknowns=list(unresolved_unknowns or []),
            active_proposal_refs=[value.id for value in proposals],
            commitment_refs=[value.id for value in commitments],
            work_refs=work_refs,
            reservation_refs=[value.id for value in reservations],
            evidence_refs=list(evidence_refs or []),
            qualification_dependency_refs=list(qualification_dependency_refs or []),
            reopen_conditions=list(reopen_conditions or []),
            stop_conditions=list(stop_conditions or []),
            escalation_conditions=list(escalation_conditions or []),
        )
        return self._save_append_only(snapshot)  # type: ignore[return-value]

    def handoff(self, handoff: ResponsibilityHandoff) -> ResponsibilityHandoff:
        snapshot = self._get(handoff.context_snapshot_ref, ResponsibilityContextSnapshot)
        if snapshot.responsibility_ref != handoff.responsibility_ref:
            raise ValueError("handoff context snapshot belongs to another responsibility")
        if snapshot.responsibility_version != handoff.responsibility_version:
            raise ValueError("handoff context snapshot version mismatch")
        from_binding = self._get(handoff.from_session_ref, ReasoningSessionBinding)
        to_binding = self._get(handoff.to_session_ref, ReasoningSessionBinding)
        if (
            from_binding.responsibility_ref != handoff.responsibility_ref
            or to_binding.responsibility_ref != handoff.responsibility_ref
        ):
            raise ValueError("handoff session responsibility mismatch")
        return self._save_append_only(handoff)  # type: ignore[return-value]

    def validate_handoff(
        self,
        handoff_id: str,
        *,
        now: datetime,
    ) -> ContinuityValidation:
        handoff = self._get(handoff_id, ResponsibilityHandoff)
        snapshot = self._get(handoff.context_snapshot_ref, ResponsibilityContextSnapshot)
        version, _statement, scope = self.current_definition(handoff.responsibility_ref)
        active = self.current_status(handoff.responsibility_ref) is ResponsibilityStatus.ACTIVE
        scope_current = version == snapshot.responsibility_version and scope == snapshot.scope

        assessments_current = True
        for ref in snapshot.open_assessment_refs:
            value = self._get(ref, ResponsibilityAssessment)
            if value.responsibility_version != version or (
                value.fresh_until is not None and now > value.fresh_until
            ):
                assessments_current = False
                break

        expectations_current = True
        for ref in snapshot.open_expectation_refs:
            value = self._get(ref, ResponsibilityExpectation)
            if value.responsibility_version != version or not self.expectation_open(ref):
                expectations_current = False
                break

        proposals_current = True
        for ref in snapshot.active_proposal_refs:
            value = self._get(ref, WorkProposal)
            if value.responsibility_version != version or (
                value.fresh_until is not None and now > value.fresh_until
            ):
                proposals_current = False
                break

        reservations_current = True
        for ref in snapshot.reservation_refs:
            value = self._get(ref, ResourceReservation)
            if self._reservation_released(value, now=now):
                reservations_current = False
                break

        validation = ContinuityValidation(
            id=_stable_id("continuity", handoff.id, version, now.isoformat()),
            responsibility_ref=handoff.responsibility_ref,
            responsibility_version=version,
            handoff_ref=handoff.id,
            responsibility_active=active,
            scope_current=scope_current,
            assessment_current=assessments_current,
            expectations_current=expectations_current,
            proposals_current=proposals_current,
            reservations_current=reservations_current,
            authorization_revalidation_required=True,
            validated_at=now,
            rationale=(
                "handoff preserves durable responsibility history but never transfers "
                "or extends execution authority"
            ),
        )
        return self._save_append_only(validation)  # type: ignore[return-value]


__all__ = ["ResponsibilityKernel"]
