from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any, cast

from portable_runtime.controller.models import ControllerDecision
from portable_runtime.controller.policy import ControllerPolicy
from portable_runtime.controller.service import (
    CONTROLLER_DECISION_EVENT,
    CONTROLLER_RESULT_EVENT,
    CognitiveController,
)
from portable_runtime.core.models import Event


def _version_value(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _controller_state_version(event: Event) -> int | None:
    """Read the durable controller chronology version from an event."""

    for payload in (event.metadata, event.payload):
        version = _version_value(payload.get("controller_state_version"))
        if version is not None:
            return version
        version = _version_value(payload.get("state_version"))
        if version is not None:
            return version

    decision = event.payload.get("decision")
    if isinstance(decision, dict):
        version = _version_value(decision.get("controller_state_version"))
        if version is not None:
            return version
        version = _version_value(decision.get("state_version"))
        if version is not None:
            return version
    return None


def _chronology_key(
    event: Event,
    logical_version: int | None = None,
) -> tuple[int, datetime, str]:
    """Order controller projections by state version before wall-clock ties."""

    if logical_version is None:
        logical_version = _controller_state_version(event)
    return (logical_version if logical_version is not None else -1, event.created_at, event.id)


def latest_controller_decision(
    controller: CognitiveController,
    controller_id: str,
) -> ControllerDecision | None:
    """Return the latest durable controller decision for external policy plugins.

    Store list ordering is not part of the controller plugin contract. Select by
    controller state version first, with event time and id only as same-version
    tie-breakers, so memory/SQLite ordering cannot invert the policy stage
    projection.

    This is a read projection over canonical controller history; it creates no
    second decision store and grants no authority.
    """

    latest_key: tuple[int, datetime, str] | None = None
    latest_decision: ControllerDecision | None = None
    for event in controller.store.list_events(controller_id):
        if event.type != CONTROLLER_DECISION_EVENT:
            continue
        raw = event.payload.get("decision")
        if not isinstance(raw, dict):
            continue
        decision = ControllerDecision.model_validate(raw)
        key = _chronology_key(event, _controller_state_version(event))
        if latest_key is None or key > latest_key:
            latest_key = key
            latest_decision = decision
    return latest_decision


def controller_capability_result(
    controller: CognitiveController,
    controller_id: str,
    decision_ref: str,
) -> dict[str, Any] | None:
    """Read the latest durable capability result for one controller decision."""

    latest_key: tuple[int, datetime, str] | None = None
    result: dict[str, Any] | None = None
    for event in controller.store.list_events(controller_id):
        if event.type != CONTROLLER_RESULT_EVENT:
            continue
        if event.payload.get("decision_ref") != decision_ref:
            continue
        raw = event.payload.get("result")
        key = _chronology_key(event)
        if isinstance(raw, dict) and (latest_key is None or key > latest_key):
            latest_key = key
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
