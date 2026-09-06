from datetime import UTC, datetime

from portable_runtime.controller import (
    CognitiveController,
    ControllerDecision,
    ControllerDecisionKind,
    controller_capability_result,
    latest_controller_decision,
)
from portable_runtime.controller.service import (
    CONTROLLER_DECISION_EVENT,
    CONTROLLER_RESULT_EVENT,
)
from portable_runtime.core.models import Event
from portable_runtime.core.runtime import Runtime


def test_latest_controller_decision_uses_event_chronology_not_store_order() -> None:
    runtime = Runtime(runtime_id="projection-order")
    controller = CognitiveController(runtime)
    controller_id = "controller:test"
    older = ControllerDecision(
        id="decision:older",
        controller_ref=controller_id,
        state_version=1,
        kind=ControllerDecisionKind.WAIT,
        reason="old stage",
    )
    newer = ControllerDecision(
        id="decision:newer",
        controller_ref=controller_id,
        state_version=2,
        kind=ControllerDecisionKind.REOPEN,
        reason="new stage",
    )

    runtime.store.append_event(
        Event(
            id="event:newer",
            type=CONTROLLER_DECISION_EVENT,
            subject_ref=controller_id,
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
            payload={"decision": newer.model_dump(mode="json")},
        )
    )
    runtime.store.append_event(
        Event(
            id="event:older",
            type=CONTROLLER_DECISION_EVENT,
            subject_ref=controller_id,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            payload={"decision": older.model_dump(mode="json")},
        )
    )

    projected = latest_controller_decision(controller, controller_id)

    assert projected is not None
    assert projected.id == newer.id
    assert projected.kind is ControllerDecisionKind.REOPEN


def test_controller_capability_result_uses_latest_result_event() -> None:
    runtime = Runtime(runtime_id="result-order")
    controller = CognitiveController(runtime)
    controller_id = "controller:test"
    decision_ref = "decision:test"

    runtime.store.append_event(
        Event(
            id="event:result-newer",
            type=CONTROLLER_RESULT_EVENT,
            subject_ref=controller_id,
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
            payload={
                "decision_ref": decision_ref,
                "result": {"status": "succeeded", "message": "new reality"},
            },
        )
    )
    runtime.store.append_event(
        Event(
            id="event:result-older",
            type=CONTROLLER_RESULT_EVENT,
            subject_ref=controller_id,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            payload={
                "decision_ref": decision_ref,
                "result": {"status": "failed", "message": "stale reality"},
            },
        )
    )

    result = controller_capability_result(controller, controller_id, decision_ref)

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["message"] == "new reality"
