from __future__ import annotations

from typing import Any

from portable_runtime.controller.closure import CognitiveClosure
from portable_runtime.controller.models import (
    ControllerDecision,
    ControllerDecisionKind,
    ControllerState,
    ControllerStatus,
)
from portable_runtime.controller.policy import ControllerPolicy
from portable_runtime.controller.revision import RevisionAssessment, RevisionDisposition
from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Event, new_id, utcnow
from portable_runtime.responsibility.models import EffectClass, WorkProposal
from portable_runtime.responsibility.service import ResponsibilityKernel

CONTROLLER_STATE_EVENT = "ControllerStateRecorded"
CONTROLLER_DECISION_EVENT = "ControllerDecisionSelected"
CONTROLLER_RESULT_EVENT = "ControllerCapabilityResultObserved"
CONTROLLER_CLOSURE_EVENT = "ControllerCognitiveClosureFormed"
CONTROLLER_WORK_PROPOSAL_EVENT = "ControllerWorkProposalHandedOff"
CONTROLLER_REVISION_EVENT = "ControllerRevisionAssessed"
CONTROLLER_REOPEN_REQUIRED_EVENT = "ControllerReopenRequired"

_UNCHANGED = object()


class CognitiveController:
    """Durable cognitive-control state machine over the existing runtime.

    The controller selects cognitive/work direction and preserves closure/revision
    lineage. It does not own provider truth, Work admission, execution authority,
    external effects, verification or responsibility discharge.
    """

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.store = runtime.store
        self.responsibilities = ResponsibilityKernel(self.store)

    def create(
        self,
        *,
        responsibility_ref: str | None = None,
        subject_ref: str | None = None,
        context_refs: list[str] | None = None,
        candidate_refs: list[str] | None = None,
        open_issue_refs: list[str] | None = None,
        controller_id: str | None = None,
    ) -> ControllerState:
        state = ControllerState(
            id=controller_id or new_id("controller"),
            responsibility_ref=responsibility_ref,
            subject_ref=subject_ref,
            context_refs=list(context_refs or []),
            candidate_refs=list(candidate_refs or []),
            open_issue_refs=list(open_issue_refs or []),
        )
        if self.get(state.id) is not None:
            raise ValueError(f"controller state already exists: {state.id}")
        self._record_state(state)
        return state

    def get(self, controller_id: str) -> ControllerState | None:
        states: list[ControllerState] = []
        for event in self.store.list_events(controller_id):
            if event.type != CONTROLLER_STATE_EVENT:
                continue
            raw = event.payload.get("state")
            if isinstance(raw, dict):
                states.append(ControllerState.model_validate(raw))
        if not states:
            return None
        return max(states, key=lambda state: (state.version, state.updated_at))

    def decisions(self, controller_id: str) -> list[ControllerDecision]:
        values: list[ControllerDecision] = []
        for event in self.store.list_events(controller_id):
            if event.type != CONTROLLER_DECISION_EVENT:
                continue
            raw = event.payload.get("decision")
            if isinstance(raw, dict):
                values.append(ControllerDecision.model_validate(raw))
        return values

    def closures(self, controller_id: str) -> list[CognitiveClosure]:
        values: list[CognitiveClosure] = []
        for event in self.store.list_events(controller_id):
            if event.type != CONTROLLER_CLOSURE_EVENT:
                continue
            raw = event.payload.get("closure")
            if isinstance(raw, dict):
                values.append(CognitiveClosure.model_validate(raw))
        return values

    def get_closure(self, controller_id: str, closure_id: str) -> CognitiveClosure | None:
        return next((value for value in self.closures(controller_id) if value.id == closure_id), None)

    def revisions(self, controller_id: str) -> list[RevisionAssessment]:
        values: list[RevisionAssessment] = []
        for event in self.store.list_events(controller_id):
            if event.type != CONTROLLER_REVISION_EVENT:
                continue
            raw = event.payload.get("revision")
            if isinstance(raw, dict):
                values.append(RevisionAssessment.model_validate(raw))
        return values

    async def step(self, controller_id: str, policy: ControllerPolicy) -> ControllerState:
        """Ask one policy for one selection, then apply it through normal guards."""

        state = self.get(controller_id)
        if state is None:
            raise ValueError(f"unknown controller state: {controller_id}")
        policy_ref = policy.policy_ref.strip()
        if not policy_ref:
            raise ValueError("controller policy_ref cannot be blank")

        decision = await policy.select(state.model_copy(deep=True))
        if decision.controller_ref != state.id:
            raise ValueError("controller policy selected a decision for another controller")
        if decision.state_version != state.version:
            raise ValueError(
                f"controller policy selected stale state version {decision.state_version}; "
                f"current version is {state.version}"
            )
        decision = decision.model_copy(update={"policy_ref": policy_ref})
        return await self.apply(decision)

    async def apply(self, decision: ControllerDecision) -> ControllerState:
        state = self._require_current(decision)
        self._record_decision(decision)

        if decision.kind is ControllerDecisionKind.INVOKE_CAPABILITY:
            return await self._invoke_capability(state, decision)
        if decision.kind is ControllerDecisionKind.FORM_CLOSURE:
            return self._form_closure(state, decision)
        if decision.kind is ControllerDecisionKind.PROPOSE_WORK:
            return self._propose_work(state, decision)
        if decision.kind is ControllerDecisionKind.ASSESS_REVISION:
            return self._assess_revision(state, decision)
        if decision.kind is ControllerDecisionKind.CLOSE:
            return self._transition(
                state,
                decision,
                status=ControllerStatus.CLOSED,
                pending_ref=None,
            )
        if decision.kind is ControllerDecisionKind.REOPEN:
            return self._transition(
                state,
                decision,
                status=ControllerStatus.OPEN,
                pending_ref=None,
                active_closure_ref=None,
                work_proposal_ref=None,
            )
        if decision.kind is ControllerDecisionKind.WAIT:
            return self._transition(
                state,
                decision,
                status=ControllerStatus.WAITING,
                pending_ref=decision.id,
            )
        raise ValueError(f"unsupported controller decision kind: {decision.kind}")

    def reopen_required(self, controller_id: str, *, reason: str) -> ControllerState:
        state = self.get(controller_id)
        if state is None:
            raise ValueError(f"unknown controller state: {controller_id}")
        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_REOPEN_REQUIRED_EVENT,
                subject_ref=state.id,
                payload={"reason": reason, "from_version": state.version},
            )
        )
        next_state = state.model_copy(
            update={
                "status": ControllerStatus.REOPEN_REQUIRED,
                "version": state.version + 1,
                "pending_ref": None,
                "updated_at": utcnow(),
            }
        )
        self._record_state(next_state)
        return next_state

    def _require_current(self, decision: ControllerDecision) -> ControllerState:
        state = self.get(decision.controller_ref)
        if state is None:
            raise ValueError(f"unknown controller state: {decision.controller_ref}")
        if decision.state_version != state.version:
            raise ValueError(
                f"stale controller decision: expected state version {state.version}, "
                f"got {decision.state_version}"
            )

        if state.status is ControllerStatus.OPEN:
            if state.active_closure_ref is None:
                allowed = {
                    ControllerDecisionKind.INVOKE_CAPABILITY,
                    ControllerDecisionKind.FORM_CLOSURE,
                    ControllerDecisionKind.CLOSE,
                    ControllerDecisionKind.WAIT,
                }
            else:
                allowed = {
                    ControllerDecisionKind.PROPOSE_WORK,
                    ControllerDecisionKind.CLOSE,
                    ControllerDecisionKind.WAIT,
                }
        elif state.status is ControllerStatus.WAITING:
            if state.active_closure_ref is not None and state.work_proposal_ref is not None:
                allowed = {ControllerDecisionKind.ASSESS_REVISION}
            else:
                allowed = {ControllerDecisionKind.REOPEN}
        elif state.status in {ControllerStatus.CLOSED, ControllerStatus.REOPEN_REQUIRED}:
            allowed = {ControllerDecisionKind.REOPEN}
        else:  # pragma: no cover - StrEnum exhaustiveness guard
            allowed = set()

        if decision.kind not in allowed:
            if state.status is ControllerStatus.OPEN and state.active_closure_ref is not None:
                raise ValueError(
                    "active cognitive closure admits only propose-work, close, or wait; "
                    "explicit reopen is required before further exploration"
                )
            if state.status is ControllerStatus.WAITING and state.work_proposal_ref is not None:
                raise ValueError(
                    "handed-off Work requires RevisionAssessment before retry, reopen, or close"
                )
            if state.status is ControllerStatus.OPEN:
                raise ValueError(f"open controller state does not admit {decision.kind.value}")
            raise ValueError(
                f"{state.status.value} controller state does not admit {decision.kind.value}"
            )
        return state

    async def _invoke_capability(
        self,
        state: ControllerState,
        decision: ControllerDecision,
    ) -> ControllerState:
        if decision.capability is None:
            raise ValueError("invoke-capability decision has no capability")
        request_id = new_id("request")
        waiting = state.model_copy(
            update={
                "status": ControllerStatus.WAITING,
                "version": state.version + 1,
                "pending_ref": request_id,
                "last_decision_ref": decision.id,
                "updated_at": utcnow(),
            }
        )
        self._record_state(waiting)

        request = CapabilityRequest(
            id=request_id,
            capability=decision.capability,
            instruction=decision.instruction,
            parameters=dict(decision.parameters),
            constraints=dict(decision.constraints),
            effect_class="read",
            metadata={
                "controller_ref": state.id,
                "controller_decision_ref": decision.id,
                "controller_state_version": state.version,
            },
        )
        result = await self.runtime.invoke(request)
        result_event = Event(
            id=new_id("event"),
            type=CONTROLLER_RESULT_EVENT,
            subject_ref=state.id,
            payload={
                "decision_ref": decision.id,
                "request_ref": request.id,
                "controller_state_version": state.version,
                "result": result.model_dump(mode="json"),
            },
        )
        self.store.append_event(result_event)

        resumed = waiting.model_copy(
            update={
                "status": ControllerStatus.OPEN,
                "version": waiting.version + 1,
                "pending_ref": None,
                "last_result_ref": result_event.id,
                "updated_at": utcnow(),
            }
        )
        self._record_state(resumed)
        return resumed

    def _form_closure(
        self,
        state: ControllerState,
        decision: ControllerDecision,
    ) -> ControllerState:
        closure = decision.closure
        if closure is None:
            raise ValueError("form-closure decision has no closure")
        if state.responsibility_ref != closure.responsibility_ref:
            raise ValueError("closure responsibility_ref does not match controller state")
        if state.subject_ref != closure.subject_ref:
            raise ValueError("closure subject_ref does not match controller state")
        if state.candidate_refs and not set(closure.selected_candidate_refs).issubset(
            state.candidate_refs
        ):
            raise ValueError("closure selected_candidate_refs are not current controller candidates")
        missing_issue_dispositions = set(state.open_issue_refs) - set(closure.deferred_issue_refs)
        if missing_issue_dispositions:
            raise ValueError(
                "closure must explicitly defer every unresolved controller issue: "
                + ", ".join(sorted(missing_issue_dispositions))
            )
        if decision.policy_ref is not None:
            if closure.policy_ref not in {None, decision.policy_ref}:
                raise ValueError("closure policy_ref conflicts with controller decision")
            closure = closure.model_copy(update={"policy_ref": decision.policy_ref})
        event = Event(
            id=new_id("event"),
            type=CONTROLLER_CLOSURE_EVENT,
            subject_ref=state.id,
            payload={
                "decision_ref": decision.id,
                "closure": closure.model_dump(mode="json"),
            },
        )
        self.store.append_event(event)
        return self._transition(
            state,
            decision,
            status=ControllerStatus.OPEN,
            pending_ref=None,
            active_closure_ref=closure.id,
            last_result_ref=event.id,
        )

    def _propose_work(
        self,
        state: ControllerState,
        decision: ControllerDecision,
    ) -> ControllerState:
        if state.responsibility_ref is None:
            raise ValueError("propose-work requires controller responsibility_ref")
        if state.subject_ref is None:
            raise ValueError("propose-work requires controller subject_ref")
        if decision.assessment_ref is None or decision.work_title is None:
            raise ValueError("propose-work decision is incomplete")
        closure_ref = decision.closure_ref
        if closure_ref is None or closure_ref != state.active_closure_ref:
            raise ValueError("propose-work must reference the active cognitive closure")
        closure = self.get_closure(state.id, closure_ref)
        if closure is None:
            raise ValueError("active cognitive closure is unavailable")
        if EffectClass(decision.effect_class) != closure.effect_class:
            raise ValueError("work effect_class exceeds or differs from cognitive closure")
        if not set(decision.requested_capabilities).issubset(closure.requested_capabilities):
            raise ValueError("work requests capabilities outside cognitive closure")

        responsibility_version, _statement, _scope = self.responsibilities.current_definition(
            state.responsibility_ref
        )
        proposal = WorkProposal(
            responsibility_ref=state.responsibility_ref,
            responsibility_version=responsibility_version,
            assessment_ref=decision.assessment_ref,
            subject_ref=state.subject_ref,
            work_kind=decision.work_kind,
            title=decision.work_title,
            description=decision.work_description,
            requested_capabilities=(
                list(decision.requested_capabilities)
                if decision.requested_capabilities
                else list(closure.requested_capabilities)
            ),
            expected_result=decision.expected_result or "; ".join(closure.acceptance_criteria),
            stop_conditions=(
                list(decision.stop_conditions)
                if decision.stop_conditions
                else list(closure.stop_conditions)
            ),
            escalation_conditions=(
                list(decision.escalation_conditions)
                if decision.escalation_conditions
                else list(closure.escalation_conditions)
            ),
            effect_class=closure.effect_class,
        )
        proposal = self.responsibilities.propose(proposal, now=utcnow())
        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_WORK_PROPOSAL_EVENT,
                subject_ref=state.id,
                payload={
                    "decision_ref": decision.id,
                    "closure_ref": closure.id,
                    "proposal_ref": proposal.id,
                    "responsibility_ref": state.responsibility_ref,
                },
            )
        )
        return self._transition(
            state,
            decision,
            status=ControllerStatus.WAITING,
            pending_ref=proposal.id,
            work_proposal_ref=proposal.id,
            last_result_ref=proposal.id,
        )

    def _assess_revision(
        self,
        state: ControllerState,
        decision: ControllerDecision,
    ) -> ControllerState:
        revision = decision.revision
        if revision is None:
            raise ValueError("assess-revision decision has no revision")
        if state.active_closure_ref is None:
            raise ValueError("revision requires an active cognitive closure")
        if state.work_proposal_ref is None:
            raise ValueError("revision requires a handed-off WorkProposal")
        if revision.closure_ref != state.active_closure_ref:
            raise ValueError("revision does not refer to the active cognitive closure")
        work = self.store.get_work(revision.work_ref)
        if work is None:
            raise ValueError("revision work_ref does not identify a durable Work")
        if work.metadata.get("responsibility_proposal_ref") != state.work_proposal_ref:
            raise ValueError("revision Work does not descend from the current WorkProposal")
        if decision.policy_ref is not None:
            if revision.policy_ref not in {None, decision.policy_ref}:
                raise ValueError("revision policy_ref conflicts with controller decision")
            revision = revision.model_copy(update={"policy_ref": decision.policy_ref})

        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_REVISION_EVENT,
                subject_ref=state.id,
                payload={
                    "decision_ref": decision.id,
                    "revision": revision.model_dump(mode="json"),
                },
            )
        )

        if revision.recommended_disposition is RevisionDisposition.CLOSE:
            status = ControllerStatus.CLOSED
            pending_ref: str | None = None
        elif revision.recommended_disposition in {
            RevisionDisposition.REVISE_WORK,
            RevisionDisposition.REOPEN_COGNITION,
            RevisionDisposition.ACQUIRE_EVIDENCE,
        }:
            status = ControllerStatus.REOPEN_REQUIRED
            pending_ref = None
        else:
            status = ControllerStatus.WAITING
            pending_ref = revision.id

        return self._transition(
            state,
            decision,
            status=status,
            pending_ref=pending_ref,
            last_revision_ref=revision.id,
            last_result_ref=revision.id,
        )

    def _transition(
        self,
        state: ControllerState,
        decision: ControllerDecision,
        *,
        status: ControllerStatus,
        pending_ref: str | None,
        active_closure_ref: str | None | object = _UNCHANGED,
        work_proposal_ref: str | None | object = _UNCHANGED,
        last_revision_ref: str | None | object = _UNCHANGED,
        last_result_ref: str | None | object = _UNCHANGED,
    ) -> ControllerState:
        update: dict[str, Any] = {
            "status": status,
            "version": state.version + 1,
            "pending_ref": pending_ref,
            "last_decision_ref": decision.id,
            "updated_at": utcnow(),
        }
        if active_closure_ref is not _UNCHANGED:
            update["active_closure_ref"] = active_closure_ref
        if work_proposal_ref is not _UNCHANGED:
            update["work_proposal_ref"] = work_proposal_ref
        if last_revision_ref is not _UNCHANGED:
            update["last_revision_ref"] = last_revision_ref
        if last_result_ref is not _UNCHANGED:
            update["last_result_ref"] = last_result_ref
        next_state = state.model_copy(update=update)
        self._record_state(next_state)
        return next_state

    def _record_state(self, state: ControllerState) -> None:
        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_STATE_EVENT,
                subject_ref=state.id,
                payload={"state": state.model_dump(mode="json")},
            )
        )

    def _record_decision(self, decision: ControllerDecision) -> None:
        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_DECISION_EVENT,
                subject_ref=decision.controller_ref,
                payload={"decision": decision.model_dump(mode="json")},
            )
        )
