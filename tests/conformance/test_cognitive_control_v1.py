from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from portable_runtime.controller import (
    CognitiveController,
    ControllerDecision,
    ControllerDecisionKind,
    ControllerStatus,
)
from portable_runtime.controller.service import CONTROLLER_RESULT_EVENT
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import utcnow
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
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="candidate explanation",
            metadata={"candidate": True},
        )

    async def cancel(self, request_id: str) -> None:
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
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


@pytest.mark.asyncio
async def test_reasoner_result_remains_controller_evidence_not_work_or_truth() -> None:
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
    assert runtime.list_work() == []
    assert runtime.store.list_knowledge() == []
    assert result_state.last_result_ref is not None
    event = runtime.store.get_event(result_state.last_result_ref)
    assert event is not None
    assert event.type == CONTROLLER_RESULT_EVENT
    assert event.payload["result"]["message"] == "candidate explanation"

    with pytest.raises(ValueError, match="stale controller decision"):
        await controller.apply(
            ControllerDecision(
                controller_ref=state.id,
                state_version=0,
                kind=ControllerDecisionKind.CLOSE,
            )
        )


@pytest.mark.asyncio
async def test_controller_work_handoff_stops_at_work_proposal() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        context_refs=[assessment_ref],
    )

    result_state = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.PROPOSE_WORK,
            assessment_ref=assessment_ref,
            work_title="Inspect service health",
            work_description="Collect current health evidence",
            requested_capabilities=["observe.health"],
            expected_result="fresh health evidence",
        )
    )

    assert runtime.list_work() == []
    assert result_state.last_result_ref is not None
    proposal = kernel.journal.get(result_state.last_result_ref)
    assert isinstance(proposal, WorkProposal)
    assert proposal.assessment_ref == assessment_ref
    assert kernel.current_status(responsibility.id) is ResponsibilityStatus.ACTIVE


@pytest.mark.asyncio
async def test_controller_close_does_not_discharge_responsibility() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    kernel, responsibility, assessment_ref = _register_responsibility(runtime.store)
    controller = CognitiveController(runtime)
    state = controller.create(
        responsibility_ref=responsibility.id,
        subject_ref="service:example",
        context_refs=[assessment_ref],
    )

    closed = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.CLOSE,
            reason="current cognitive question is sufficiently bounded",
        )
    )

    assert closed.status is ControllerStatus.CLOSED
    assert runtime.list_work() == []
    assert kernel.current_status(responsibility.id) is ResponsibilityStatus.ACTIVE


@pytest.mark.asyncio
async def test_waiting_state_requires_explicit_reopen() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    controller = CognitiveController(runtime)
    state = controller.create()
    waiting = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.WAIT,
            reason="await external evidence",
        )
    )
    assert waiting.status is ControllerStatus.WAITING

    with pytest.raises(ValueError, match="explicitly reopened"):
        await controller.apply(
            ControllerDecision(
                controller_ref=state.id,
                state_version=waiting.version,
                kind=ControllerDecisionKind.CLOSE,
            )
        )

    reopened = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=waiting.version,
            kind=ControllerDecisionKind.REOPEN,
            reason="new evidence arrived",
        )
    )
    assert reopened.status is ControllerStatus.OPEN


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
