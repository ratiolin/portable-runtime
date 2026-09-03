from __future__ import annotations

from typing import Any

from portable_runtime.controller.models import (
    ControllerDecision,
    ControllerDecisionKind,
    ControllerState,
    ControllerStatus,
)
from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Event, new_id, utcnow
from portable_runtime.responsibility.models import EffectClass, WorkProposal
from portable_runtime.responsibility.service import ResponsibilityKernel

CONTROLLER_STATE_EVENT = "ControllerStateRecorded"
CONTROLLER_DECISION_EVENT = "ControllerDecisionSelected"
CONTROLLER_RESULT_EVENT = "ControllerCapabilityResultObserved"
CONTROLLER_WORK_PROPOSAL_EVENT = "ControllerWorkProposalHandedOff"
CONTROLLER_REOPEN_REQUIRED_EVENT = "ControllerReopenRequired"


class CognitiveController:
    """Minimal cognitive-control state machine over the existing runtime.

    The controller selects cognitive/work direction. It does not own provider
    truth, Work admission, execution authorization, external effects,
    verification or responsibility discharge.
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

    async def apply(self, decision: ControllerDecision) -> ControllerState:
        state = self._require_current(decision)
        self._record_decision(decision)

        if decision.kind is ControllerDecisionKind.INVOKE_CAPABILITY:
            return await self._invoke_capability(state, decision)
        if decision.kind is ControllerDecisionKind.PROPOSE_WORK:
            return self._propose_work(state, decision)
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
        if state.status is ControllerStatus.WAITING and decision.kind is not ControllerDecisionKind.REOPEN:
            raise ValueError("waiting controller state must be explicitly reopened before a new decision")
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
            requested_capabilities=list(decision.requested_capabilities),
            expected_result=decision.expected_result,
            stop_conditions=list(decision.stop_conditions),
            escalation_conditions=list(decision.escalation_conditions),
            effect_class=EffectClass(decision.effect_class),
        )
        proposal = self.responsibilities.propose(proposal, now=utcnow())
        self.store.append_event(
            Event(
                id=new_id("event"),
                type=CONTROLLER_WORK_PROPOSAL_EVENT,
                subject_ref=state.id,
                payload={
                    "decision_ref": decision.id,
                    "proposal_ref": proposal.id,
                    "responsibility_ref": state.responsibility_ref,
                },
            )
        )
        return self._transition(
            state,
            decision,
            status=ControllerStatus.OPEN,
            pending_ref=None,
            last_result_ref=proposal.id,
        )

    def _transition(
        self,
        state: ControllerState,
        decision: ControllerDecision,
        *,
        status: ControllerStatus,
        pending_ref: str | None,
        last_result_ref: str | None = None,
    ) -> ControllerState:
        next_state = state.model_copy(
            update={
                "status": status,
                "version": state.version + 1,
                "pending_ref": pending_ref,
                "last_decision_ref": decision.id,
                "last_result_ref": last_result_ref if last_result_ref is not None else state.last_result_ref,
                "updated_at": utcnow(),
            }
        )
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
