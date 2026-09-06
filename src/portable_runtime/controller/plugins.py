from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from portable_runtime.controller.models import ControllerDecision
from portable_runtime.controller.policy import ControllerPolicy
from portable_runtime.controller.service import (
    CONTROLLER_DECISION_EVENT,
    CONTROLLER_RESULT_EVENT,
    CognitiveController,
)


def latest_controller_decision(
    controller: CognitiveController,
    controller_id: str,
) -> ControllerDecision | None:
    """Return the latest durable controller decision for external policy plugins.

    This is a read projection over canonical controller history; it creates no
    second decision store and grants no authority.
    """

    decisions: list[ControllerDecision] = []
    for event in controller.store.list_events(controller_id):
        if event.type != CONTROLLER_DECISION_EVENT:
            continue
        raw = event.payload.get("decision")
        if isinstance(raw, dict):
            decisions.append(ControllerDecision.model_validate(raw))
    return decisions[-1] if decisions else None


def controller_capability_result(
    controller: CognitiveController,
    controller_id: str,
    decision_ref: str,
) -> dict[str, Any] | None:
    """Read the durable capability result produced for one controller decision."""

    result: dict[str, Any] | None = None
    for event in controller.store.list_events(controller_id):
        if event.type != CONTROLLER_RESULT_EVENT:
            continue
        if event.payload.get("decision_ref") != decision_ref:
            continue
        raw = event.payload.get("result")
        if isinstance(raw, dict):
            result = dict(raw)
    return result


def load_controller_policy(spec: str, /, **kwargs: Any) -> ControllerPolicy:
    """Load an external ControllerPolicy factory from ``module:attribute``.

    Agent Kernel remains provider/policy neutral: the external object owns only
    selection logic and is still constrained by ``CognitiveController.step`` and
    normal runtime admissibility/authority checks.
    """

    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("controller policy plugin must use 'module:attribute' syntax")

    module = import_module(module_name.strip())
    factory = getattr(module, attribute.strip(), None)
    if factory is None or not callable(factory):
        raise TypeError(f"controller policy plugin target is not callable: {spec}")

    policy = factory(**kwargs)
    policy_ref = getattr(policy, "policy_ref", None)
    select = getattr(policy, "select", None)
    if not isinstance(policy_ref, str) or not policy_ref.strip() or not callable(select):
        raise TypeError("loaded object does not satisfy the ControllerPolicy boundary")
    return cast(ControllerPolicy, policy)
