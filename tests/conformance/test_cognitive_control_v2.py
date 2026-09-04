from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from portable_runtime.controller import (
    CognitiveClosure,
    CognitiveController,
    ControllerDecision,
    ControllerDecisionKind,
    ControllerStatus,
    RevisionAssessment,
    RevisionDisposition,
    RevisionScope,
)
from portable_runtime.controller.service import CONTROLLER_RESULT_EVENT
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import Work, utcnow
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.responsibility.models import (
    ResponsibilityAdmission,
    ResponsibilityExpectation,
    ResponsibilityStatus,
    StandingResponsibility,
    WorkProposal,
)
from portable_runtime.responsibility.service import ResponsibilityKernel
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


class ReasonProvider:
    def __init__(self) -> None:
        self._descriptor = ProviderDescriptor(
            id="reasoner",
            name="reasoner",
            version="1",
            capabilities=["reason.generate"],
            effect_semantics="pure",
            side_effect_class="pure",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        del context
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="candidate explanation",
            metadata={"candidate": True},
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        del request_id
        return None


def _runtime_with_reasoner(store=None) -> Runtime:
    registry = ProviderRegistry()
    registry.register(ReasonProvider())
    return Runtime(store=store or InMemoryStateStore(), registry=registry)


def _register_responsibility(store) -> tuple[ResponsibilityKernel, StandingResponsibility, str]:
    kernel = ResponsibilityKernel(store)
    responsibility = StandingResponsibility(
        id="resp_controller",
        responsibility_kind="service-health",
        statement="Keep the service healthy",
        scope={"service": "example"},
    )
    kernel.register(
        responsibility,
        ResponsibilityAdmission(
            id="resp_admission_controller",
            responsibility_ref=responsibility.id,
            responsibility_version=1,
            principal_ref="principal:test",
        ),
    )
    expectation = kernel.create_expectation(
        ResponsibilityExpectation(
            id="expectation_controller",
            responsibility_ref=responsibility.id,
            responsibility_version=1,
            subject_ref="service:example",
            expected_signal_kind="health",
            due_at=utcnow() - timedelta(seconds=1),
        )
    )
    assessment = kernel.assess_due_expectation(
        expectation.id,
        now=utcnow(),
        observed_evidence_refs=[],
    )
    assert assessment is not None
    return kernel, responsibility, assessment.id


def _closure(state, *, assessment_ref: str, capability: str = "observe.health") -> CognitiveClosure:
    return CognitiveClosure(
        controller_ref=state.id,
        controller_state_version=state.version,
        responsibility_ref=state.responsibility_ref,
        subject_ref=state.subject_ref,
        problem_ref=assessment_ref,
        basis_refs=[assessment_ref],
        selected_candidate_refs=list(state.candidate_refs),
        deferred_issue_refs=list(state.open_issue_refs),
        selected_direction="inspect current service health",
        acceptance_criteria=["fresh health evidence is available"],
        verification_plan=["verify service health from an independent observation"],
        reopen_conditions=["health evidence contradicts the selected direction"],
        requested_capabilities=[capability],
    )


def _save_descendant_work(runtime: Runtime, waiting, *, work_id: str = "work:observed") -> Work:
    assert waiting.work_proposal_ref is not None
    work = Work(
        id=work_id,
        title="Materialized descendant Work",
        metadata={"responsibility_proposal_ref": waiting.work_proposal_ref},
    )
    runtime.store.save_work(work)
    return work


@pytest.mark.asyncio
async def test_reasoner_result_remains_evidence_not_closure_or_work() -> None:
    runtime = _runtime_with_reasoner()
    controller = CognitiveController(runtime)
    state = controller.create(context_refs=["goal:diagnose"])

    result_state = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.INVOKE_CAPABILITY,
            capability="reason.generate",
            instruction="generate a candidate explanation",
        )
    )

    assert result_state.status is ControllerStatus.OPEN
    assert result_state.version == 2
    assert result_state.active_closure_ref is None
    assert runtime.list_work() == []
    assert runtime.store.list_knowledge() == []
    assert controller.closures(state.id) == []
    assert result_state.last_result_ref is not None
    event = runtime.store.get_event(result_state.last_result_ref)
    assert event is not None
    assert event.type == CONTROLLER_RESULT_EVENT


@pytest.mark.asyncio
async def test_closure_requires_explicit_open_issue_disposition() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    _kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        candidate_refs=["candidate:inspect"],
        open_issue_refs=["issue:stale-source"],
    )
    closure = CognitiveClosure(
        controller_ref=state.id,
        controller_state_version=state.version,
        responsibility_ref=state.responsibility_ref,
        subject_ref=state.subject_ref,
        basis_refs=[assessment_ref],
        selected_candidate_refs=["candidate:inspect"],
        selected_direction="inspect service",
        acceptance_criteria=["health observed"],
        verification_plan=["read health monitor"],
        reopen_conditions=["monitor contradicts expectation"],
        requested_capabilities=["observe.health"],
    )

    with pytest.raises(ValueError, match="explicitly defer"):
        await controller.apply(
            ControllerDecision(
                controller_ref=state.id,
                state_version=state.version,
                kind=ControllerDecisionKind.FORM_CLOSURE,
                closure=closure,
            )
        )


@pytest.mark.asyncio
async def test_active_closure_blocks_more_exploration_and_gates_work_proposal() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        candidate_refs=["candidate:inspect"],
        open_issue_refs=["issue:source-age"],
    )
    closure = _closure(state, assessment_ref=assessment_ref)
    closed_state = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.FORM_CLOSURE,
            closure=closure,
        )
    )
    assert closed_state.status is ControllerStatus.OPEN
    assert closed_state.active_closure_ref == closure.id

    with pytest.raises(ValueError, match="active cognitive closure"):
        await controller.apply(
            ControllerDecision(
                controller_ref=state.id,
                state_version=closed_state.version,
                kind=ControllerDecisionKind.INVOKE_CAPABILITY,
                capability="reason.generate",
            )
        )

    waiting = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=closed_state.version,
            kind=ControllerDecisionKind.PROPOSE_WORK,
            closure_ref=closure.id,
            assessment_ref=assessment_ref,
            work_title="Inspect service health",
            work_description="Collect current health evidence",
            requested_capabilities=["observe.health"],
            expected_result="fresh health evidence",
        )
    )

    assert runtime.list_work() == []
    assert waiting.status is ControllerStatus.WAITING
    assert waiting.pending_ref == waiting.work_proposal_ref
    assert waiting.active_closure_ref == closure.id
    assert waiting.work_proposal_ref is not None
    proposal = kernel.journal.get(waiting.work_proposal_ref)
    assert isinstance(proposal, WorkProposal)
    assert proposal.assessment_ref == assessment_ref
    assert kernel.current_status(responsibility.id) is ResponsibilityStatus.ACTIVE


@pytest.mark.asyncio
async def test_work_proposal_without_active_closure_is_rejected() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    _kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
    )

    with pytest.raises(ValueError, match="does not admit propose-work"):
        await controller.apply(
            ControllerDecision(
                controller_ref=state.id,
                state_version=state.version,
                kind=ControllerDecisionKind.PROPOSE_WORK,
                closure_ref="closure:missing",
                assessment_ref=assessment_ref,
                work_title="should not materialize",
            )
        )


@pytest.mark.asyncio
async def test_revision_requires_reality_evidence_and_deep_failure_cannot_retry() -> None:
    with pytest.raises(ValueError, match="outcome_refs or verification_refs"):
        RevisionAssessment(
            controller_ref="controller:1",
            controller_state_version=1,
            work_ref="work:1",
            closure_ref="closure:1",
            revision_scope=RevisionScope.EXECUTION,
            recommended_disposition=RevisionDisposition.RETRY_RUN,
            reason="failed",
        )

    with pytest.raises(ValueError, match="deep revision_scope"):
        RevisionAssessment(
            controller_ref="controller:1",
            controller_state_version=1,
            work_ref="work:1",
            closure_ref="closure:1",
            verification_refs=["verification:1"],
            revision_scope=RevisionScope.PROBLEM_DEFINITION,
            recommended_disposition=RevisionDisposition.RETRY_RUN,
            reason="problem frame failed",
        )


@pytest.mark.asyncio
async def test_revision_to_reopen_preserves_history_and_clears_current_closure_on_reopen() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    _kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        candidate_refs=["candidate:inspect"],
    )
    closure = _closure(state, assessment_ref=assessment_ref)
    closure_state = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.FORM_CLOSURE,
            closure=closure,
        )
    )
    waiting = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=closure_state.version,
            kind=ControllerDecisionKind.PROPOSE_WORK,
            closure_ref=closure.id,
            assessment_ref=assessment_ref,
            work_title="Inspect service health",
            requested_capabilities=["observe.health"],
        )
    )
    work = _save_descendant_work(runtime, waiting)
    revision = RevisionAssessment(
        controller_ref=state.id,
        controller_state_version=waiting.version,
        work_ref=work.id,
        closure_ref=closure.id,
        verification_refs=["verification:still-unhealthy"],
        reason_refs=["verification:still-unhealthy"],
        revision_scope=RevisionScope.PROBLEM_DEFINITION,
        recommended_disposition=RevisionDisposition.REOPEN_COGNITION,
        reason="the original problem framing did not explain the observed condition",
    )
    reopen_required = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=waiting.version,
            kind=ControllerDecisionKind.ASSESS_REVISION,
            revision=revision,
        )
    )
    assert reopen_required.status is ControllerStatus.REOPEN_REQUIRED
    assert reopen_required.active_closure_ref == closure.id
    assert reopen_required.last_revision_ref == revision.id

    reopened = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=reopen_required.version,
            kind=ControllerDecisionKind.REOPEN,
            reason="revision requires renewed exploration",
        )
    )
    assert reopened.status is ControllerStatus.OPEN
    assert reopened.active_closure_ref is None
    assert reopened.work_proposal_ref is None
    assert controller.get_closure(state.id, closure.id) is not None
    assert any(item.id == revision.id for item in controller.revisions(state.id))


@pytest.mark.asyncio
async def test_verified_close_revision_does_not_discharge_responsibility() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        candidate_refs=["candidate:inspect"],
    )
    closure = _closure(state, assessment_ref=assessment_ref)
    closure_state = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.FORM_CLOSURE,
            closure=closure,
        )
    )
    waiting = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=closure_state.version,
            kind=ControllerDecisionKind.PROPOSE_WORK,
            closure_ref=closure.id,
            assessment_ref=assessment_ref,
            work_title="Inspect service health",
            requested_capabilities=["observe.health"],
        )
    )
    work = _save_descendant_work(runtime, waiting)
    revision = RevisionAssessment(
        controller_ref=state.id,
        controller_state_version=waiting.version,
        work_ref=work.id,
        closure_ref=closure.id,
        verification_refs=["verification:healthy"],
        revision_scope=RevisionScope.VERIFICATION,
        recommended_disposition=RevisionDisposition.CLOSE,
        reason="independent verification confirms the bounded objective",
    )
    closed = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=waiting.version,
            kind=ControllerDecisionKind.ASSESS_REVISION,
            revision=revision,
        )
    )
    assert closed.status is ControllerStatus.CLOSED
    assert kernel.current_status(responsibility.id) is ResponsibilityStatus.ACTIVE


def test_controller_state_survives_sqlite_restart(tmp_path: Path) -> None:
    path = tmp_path / "controller.db"
    store = SQLiteStateStore(path)
    try:
        runtime = Runtime(store=store)
        controller = CognitiveController(runtime)
        state = controller.create(
            controller_id="controller_restart",
            subject_ref="subject:restart",
            context_refs=["observation:1"],
        )
    finally:
        store.close()

    reopened_store = SQLiteStateStore(path)
    try:
        reopened = CognitiveController(Runtime(store=reopened_store)).get(state.id)
        assert reopened is not None
        assert reopened.id == state.id
        assert reopened.version == state.version
        assert reopened.context_refs == ["observation:1"]
        assert reopened.subject_ref == "subject:restart"
    finally:
        reopened_store.close()
