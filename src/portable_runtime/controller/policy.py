from __future__ import annotations

from typing import Protocol

from portable_runtime.controller.models import ControllerDecision, ControllerState


class ControllerPolicy(Protocol):
    """Select one controller decision for the current durable state.

    A policy owns selection logic only. It does not execute capabilities, admit
    Work, mint authorization, or mutate controller state directly.
    """

    @property
    def policy_ref(self) -> str:
        """Stable policy/version reference retained as decision provenance."""

    async def select(self, state: ControllerState) -> ControllerDecision:
        """Return one decision bound to the supplied controller state."""
