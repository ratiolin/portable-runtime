from __future__ import annotations

import sys
from types import ModuleType

import pytest

from portable_runtime.controller import (
    CognitiveController,
    ControllerDecision,
    ControllerDecisionKind,
    ControllerState,
    controller_capability_result,
    latest_controller_decision,
    load_controller_policy,
)
from portable_runtime.core.runtime import Runtime
from portable_runtime.stores.memory import InMemoryStateStore


class PluginPolicy:
    policy_ref = "plugin:test:v1"

    async def select(self, state: ControllerState) -> ControllerDecision:
        return ControllerDecision(
            controller_ref=state.id,
            state_version=state.version,
            kind=ControllerDecisionKind.CLOSE,
            reason="plugin test",
        )


def _factory() -> PluginPolicy:
    return PluginPolicy()


def test_load_external_controller_policy_factory() -> None:
    module = ModuleType("_portable_runtime_test_plugin")
    module.factory = _factory  # type: ignore[attr-defined]
    sys.modules[module.__name__] = module
    try:
        policy = load_controller_policy(f"{module.__name__}:factory")
        assert policy.policy_ref == "plugin:test:v1"
    finally:
        sys.modules.pop(module.__name__, None)


def test_plugin_spec_must_be_explicit() -> None:
    with pytest.raises(ValueError, match="module:attribute"):
        load_controller_policy("meta_controller")


@pytest.mark.asyncio
async def test_external_policy_history_reads_are_canonical_projections() -> None:
    controller = CognitiveController(Runtime(store=InMemoryStateStore()))
    state = controller.create()
    await controller.step(state.id, PluginPolicy())

    latest = latest_controller_decision(controller, state.id)
    assert latest is not None
    assert latest.kind is ControllerDecisionKind.CLOSE
    assert latest.policy_ref == "plugin:test:v1"
    assert controller_capability_result(controller, state.id, latest.id) is None
