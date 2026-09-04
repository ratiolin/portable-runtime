from __future__ import annotations

import pytest

from portable_runtime.controller import (
    CognitiveController,
    ControllerDecision,
    ControllerDecisionKind,
    ControllerState,
    ControllerStatus,
)
from portable_runtime.core.runtime import Runtime
from portable_runtime.stores.memory import InMemoryStateStore


class ClosePolicy:
    policy_ref = "policy:test-close:v1"

    async def select(self, state: ControllerState) -> ControllerDecision:
        return ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.CLOSE,
            reason="current cognitive loop is bounded",
        )


class StalePolicy:
    policy_ref = "policy:test-stale:v1"

    async def select(self, state: ControllerState) -> ControllerDecision:
        return ControllerDecision(
            controller_ref=state.id,
            state_version=max(0, state.version - 1),
            kind=ControllerDecisionKind.CLOSE,
        )


@pytest.mark.asyncio
async def test_policy_step_records_policy_provenance() -> None:
    controller = CognitiveController(Runtime(store=InMemoryStateStore()))
    state = controller.create(context_refs=["goal:test"])

    closed = await controller.step(state.id, ClosePolicy())

    assert closed.status is ControllerStatus.CLOSED
    decisions = controller.decisions(state.id)
    assert len(decisions) == 1
    assert decisions[0].policy_ref == "policy:test-close:v1"
    assert decisions[0].state_version == state.version


@pytest.mark.asyncio
async def test_policy_step_rejects_stale_selection_before_apply() -> None:
    controller = CognitiveController(Runtime(store=InMemoryStateStore()))
    state = controller.create()
    waiting = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.WAIT,
        )
    )
    reopened = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=waiting.version,
            kind=ControllerDecisionKind.REOPEN,
        )
    )

    with pytest.raises(ValueError, match="policy selected stale state version"):
        await controller.step(reopened.id, StalePolicy())

    assert controller.decisions(reopened.id)[-1].kind is ControllerDecisionKind.REOPEN


@pytest.mark.asyncio
async def test_closed_and_reopen_required_states_require_explicit_reopen() -> None:
    controller = CognitiveController(Runtime(store=InMemoryStateStore()))
    state = controller.create()
    closed = await controller.apply(
        ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.CLOSE,
        )
    )

    with pytest.raises(ValueError, match="explicitly reopened"):
        await controller.apply(
            ControllerDecision(
                controller_ref=closed.id,
                state_version=closed.version,
                kind=ControllerDecisionKind.WAIT,
            )
        )

    reopened = await controller.apply(
        ControllerDecision(
            controller_ref=closed.id,
            state_version=closed.version,
            kind=ControllerDecisionKind.REOPEN,
        )
    )
    required = controller.reopen_required(reopened.id, reason="new contradiction")
    assert required.status is ControllerStatus.REOPEN_REQUIRED

    with pytest.raises(ValueError, match="explicitly reopened"):
        await controller.apply(
            ControllerDecision(
                controller_ref=required.id,
                state_version=required.version,
                kind=ControllerDecisionKind.CLOSE,
            )
        )

    open_again = await controller.apply(
        ControllerDecision(
            controller_ref=required.id,
            state_version=required.version,
            kind=ControllerDecisionKind.REOPEN,
        )
    )
    assert open_again.status is ControllerStatus.OPEN
